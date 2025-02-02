import logging
import plugin_registry
import os
import gitlab
import git
import urllib.parse
import re

MY_SCHEME_NAME = "gitlab"

# Examples:
# gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@7e38559d#L2-3
# gitlab://mygitlab.io/user/project/-/blob/${environment('production').last_deployment.sha}/some/path/file1.txt@7e38559d#L2-3


class GitLab(plugin_registry.contract.IPlugin):
    _url_resolver: plugin_registry.IUrlResolver

    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(logger)
        self._url_resolver = UrlResolver(logger)
        logger.info(__class__.__name__ + " plugin loaded")

    def getUrlResolver(self, scheme: str) -> plugin_registry.IUrlResolver:
        return self._url_resolver if scheme == MY_SCHEME_NAME else None


class UrlResolver(plugin_registry.IUrlResolver):
    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(logger)
        self.isVersioningSupported = True
        self._gls = {}
        self._repository_compare_cache = {}
        self._repository_content_cache = {}
        self._projects_cache = {}
        self._environments_cache = {}
        self._git_fetched_for = {}

    def _getGL(self, url: str):
        url_parsed = urllib.parse.urlparse(url)
        if url_parsed.hostname in self._gls:
            gl = self._gls[url_parsed.hostname]
        else:
            gl = gitlab.Gitlab(
                f"https://{url_parsed.hostname}",
                os.getenv("GITLAB_TOKEN"),  # TODO: Provide token as plugin config
            )
            if self._logger.isEnabledFor(logging.DEBUG):
                gl.enable_debug()  # TODO: Token leaks to output
            self._gls[url_parsed.hostname] = gl
        return gl

    def _getAndCacheProjectEnvironment(
        self, project, project_id: str, environment_name: str
    ):
        environment_cache_key = f"{project_id}:{environment_name}"
        if environment_cache_key not in self._environments_cache:
            environments = project.environments.list()
            environment_id = [e for e in environments if e.name == environment_name][
                0
            ].id
            environment = project.environments.get(environment_id)
            self._environments_cache[environment_cache_key] = environment

        return self._environments_cache[environment_cache_key]

    def _getAndCacheProject(self, gl, project_id: str):
        if project_id not in self._projects_cache:
            self._projects_cache[project_id] = gl.projects.get(project_id)
        return self._projects_cache[project_id]

    def _urlToCachedRepoPath(self, url_parsed: urllib.parse.ParseResult) -> str:
        project_path_with_leading_slash = url_parsed.path.split("/-/blob/")[0]
        return (
            f"{os.getenv('GITLAB_REPO_CACHE_DIR')}/{url_parsed.hostname}{project_path_with_leading_slash}",
            url_parsed.hostname,
            project_path_with_leading_slash,
        )

    def _calcDiff(
        self, url_parsed: urllib.parse.ParseResult, ref_from: str, ref_to: str
    ) -> tuple[git.diff.DiffIndex, str]:

        cached_repo_path, hostname, project_path_with_leading_slash = (
            self._urlToCachedRepoPath(url_parsed)
        )

        repo_and_ref_to_key = f"{hostname}{project_path_with_leading_slash}:{ref_to}"
        try:
            repo = git.Repo(cached_repo_path)
            if not self._git_fetched_for.get(repo_and_ref_to_key):
                try:
                    self._logger.info(f"Doing git fetch origin refs/heads/{ref_to} in {hostname}{project_path_with_leading_slash}")
                    repo.git.fetch("origin", f"refs/heads/{ref_to}")
                except git.exc.GitCommandError:
                    self._logger.info(f"git fetch failed. Doing git fetch origin refs/tags/{ref_to} in {hostname}{project_path_with_leading_slash}")
                    repo.git.fetch("origin", f"refs/tags/{ref_to}")
        except git.exc.NoSuchPathError:
            self._logger.info(f"Doing git clone https://oauth2:REDACTED@{hostname}{project_path_with_leading_slash}.git --branch {ref_to}")
            repo = git.Repo.clone_from(
                url=f"https://oauth2:{os.getenv('GITLAB_TOKEN')}@{hostname}{project_path_with_leading_slash}.git",
                to_path=cached_repo_path,
                branch=ref_to
            )
        self._git_fetched_for[repo_and_ref_to_key] = True

        commit_to = repo.commit(ref_to)
        ref_to_hexsha_8chars = commit_to.hexsha[:8]
        diff = repo.commit(ref_from).diff(
            commit_to, create_patch=True, minimal=True, find_renames="40%"
        )
        return diff, ref_to_hexsha_8chars

    def diff(self, url: str) -> plugin_registry.contract.IDiff | bool | None:
        gl = self._getGL(url)

        url_parsed = urllib.parse.urlparse(url)
        match = re.match(
            # Examples:
            # gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@7e38559d
            r"/(?P<project_id>.+)/-/blob/(?P<ref_to>[^/]+)/(?P<file_path>[^@#]+)@(?P<ref_from>[a-fA-F0-9]+)",
            url_parsed.path,
        )
        project_id = match.group("project_id")
        file_path = match.group("file_path")
        ref_from = match.group("ref_from")
        ref_to = match.group("ref_to")

        match = re.match(
            # Example:
            # ${environment('production').last_deployment.sha}
            # ${environment("production").last_deployment.sha}
            r"\${environment\([\"'](?P<environment_name>[^\"']+)[\"']\).last_deployment.sha}",
            ref_to,
        )
        environment_name = None
        if match:
            environment_name = match.group("environment_name")

        try:
            if url_parsed.path not in self._repository_compare_cache:
                project = self._getAndCacheProject(gl=gl, project_id=project_id)

                if environment_name:
                    environment = self._getAndCacheProjectEnvironment(
                        project=project,
                        project_id=project_id,
                        environment_name=environment_name,
                    )
                    ref_to = environment.last_deployment["sha"]

                diff, ref_to_hexsha_8chars = self._calcDiff(
                    url_parsed, ref_from, ref_to
                )
                self._repository_compare_cache[url_parsed.path] = (diff, ref_to_hexsha_8chars)
            elif self._repository_compare_cache[url_parsed.path] is None:
                return None
            compare_result, ref_to_hexsha_8chars = self._repository_compare_cache[url_parsed.path]
        except Exception as e:
            self._logger.warning(f"{type(e)}: {e}")
            self._repository_compare_cache[url_parsed.path] = None
            return None

        diff_entry_arr = [
            item for item in compare_result if item.a_path == file_path
        ]  # Expect 0 or 1 element

        if len(diff_entry_arr) == 0:
            return False  # No changes in this file

        diff_entry = diff_entry_arr[0]

        match = re.match(
            # Examples:
            # L2
            # L2-5
            r"L(?P<url_first_line_number>[0-9]+)(-(?P<url_last_line_number>[0-9]+))?",
            url_parsed.fragment,
        )
        url_first_line_number = int(match.group("url_first_line_number"))
        if match.group("url_last_line_number") is None:
            url_last_line_number = url_first_line_number
        else:
            url_last_line_number = int(match.group("url_last_line_number"))

        diff_str = diff_entry.diff.decode("utf-8")
        diff_split = re.split(r"^(@@.+@@).*$\n", diff_str, flags=re.MULTILINE)
        new_url_fragment = None
        new_first_line_number = url_first_line_number
        new_last_line_number = url_last_line_number
        new_lines_content: str = None
        was_lines_content: str = None
        for i in range(
            # The 0th element is always empty string
            1,
            len(diff_split),
            2,
        ):
            diff_chunk_header = diff_split[i]
            diff_chunk_content = diff_split[i + 1]
            match = re.match(
                # Example: @@ -2,8 +36,12 @@
                r"@@ -(?P<chunk_first_line_number>[0-9]+),(?P<chunk_line_count>[0-9]+) \+(?P<chunk_new_first_line_number>[0-9]+)(,(?P<chunk_new_line_count>[0-9]+))?",
                diff_chunk_header,
            )
            chunk_first_line_number = int(match.group("chunk_first_line_number"))
            chunk_line_count = int(match.group("chunk_line_count"))
            chunk_new_first_line_number = int(
                match.group("chunk_new_first_line_number")
            )
            chunk_new_line_count = (
                int(match.group("chunk_new_line_count"))
                if match.group("chunk_new_line_count") is not None
                else 0
            )

            shift = (chunk_new_first_line_number - chunk_first_line_number) + (
                chunk_new_line_count - chunk_line_count
            )
            if (
                url_first_line_number >= chunk_first_line_number + chunk_line_count
            ):  # The chunk is fully before the line range in URL
                new_first_line_number = url_first_line_number + shift
                new_last_line_number = url_last_line_number + shift
                continue

            if (
                url_last_line_number < chunk_first_line_number
            ):  # The chunk is fully after the line range in URL
                break

            chunk_lines_arr = diff_chunk_content.split("\n")
            in_current_line_number = chunk_first_line_number
            out_current_line_number = chunk_new_first_line_number
            new_lines_arr = []
            was_lines_arr = []
            for current_line_content in chunk_lines_arr[
                :-1
            ]:  # The last element is always empty string
                if in_current_line_number > url_last_line_number + 1:
                    break

                diff_line_change_indicator = current_line_content[0]

                if diff_line_change_indicator == " ":  # no change
                    new_lines_arr.append(current_line_content[1:])
                    was_lines_arr.append(current_line_content[1:])

                    if url_first_line_number == in_current_line_number:
                        new_first_line_number = out_current_line_number
                    if url_last_line_number == in_current_line_number:
                        new_last_line_number = out_current_line_number
                    in_current_line_number += 1
                    out_current_line_number += 1
                    if in_current_line_number > url_last_line_number:
                        break

                elif diff_line_change_indicator == "-":  # line gets removed
                    was_lines_arr.append(current_line_content[1:])
                    if url_first_line_number == in_current_line_number:
                        new_first_line_number = out_current_line_number
                    if url_last_line_number == in_current_line_number:
                        new_last_line_number = out_current_line_number - 1
                    in_current_line_number += 1

                else:  # diff_line_change_indicator == "+" # line gets inserted
                    new_lines_arr.append(current_line_content[1:])
                    if url_last_line_number <= in_current_line_number:
                        new_last_line_number = out_current_line_number
                    out_current_line_number += 1

            tmp = "\n".join(
                new_lines_arr[
                    (
                        new_first_line_number - chunk_new_first_line_number
                        if new_first_line_number - chunk_new_first_line_number > 0
                        else None
                    ) : (
                        new_last_line_number - chunk_new_first_line_number + 1
                        if new_last_line_number - chunk_new_first_line_number
                        < len(new_lines_arr)
                        else None
                    )
                ]
            )
            new_lines_content = (
                new_lines_content + "..." + tmp
                if new_lines_content is not None
                else tmp
            )

            tmp = "\n".join(
                was_lines_arr[
                    (
                        url_first_line_number - chunk_first_line_number
                        if url_first_line_number - chunk_first_line_number > 0
                        else None
                    ) : (
                        url_last_line_number - chunk_first_line_number + 1
                        if url_last_line_number - chunk_first_line_number
                        < len(was_lines_arr)
                        else None
                    )
                ]
            )
            was_lines_content = (
                was_lines_content + "..." + tmp
                if was_lines_content is not None
                else tmp
            )

            if url_last_line_number >= chunk_first_line_number + chunk_line_count:
                new_last_line_number = url_last_line_number + shift

            pass

        if new_first_line_number > new_last_line_number:
            new_url_fragment = url_parsed.fragment + "<-lines deleted"
        else:
            new_url_fragment = "L" + str(new_first_line_number)
            if new_last_line_number > new_first_line_number:
                new_url_fragment += "-"
                new_url_fragment += str(new_last_line_number)

        if (
            new_url_fragment is None or new_url_fragment == url_parsed.fragment
        ) and was_lines_content == new_lines_content:  # No changes detected
            return False

        if diff_entry.b_path is not None:
            url_parsed = url_parsed._replace(
                path=url_parsed.path.replace(
                    f"/{diff_entry.a_path}", f"/{diff_entry.b_path}"
                )
            )

        url_parsed = url_parsed._replace(fragment=new_url_fragment)._replace(
            path=re.sub(
                r"@[a-fA-F0-9]+$",
                "@" + ref_to_hexsha_8chars,
                url_parsed.path,
            )
        )

        if was_lines_content == new_lines_content:
            return plugin_registry.contract.IDiffLinesMoved(
                updated_url=url_parsed.geturl(), current_lines_content=new_lines_content
            )
        else:
            return plugin_registry.contract.IDiffContentChanged(
                updated_url=url_parsed.geturl(),
                current_lines_content=new_lines_content,
                was_lines_content=was_lines_content,
            )

    def resolveToContent(
        self, url: str
    ) -> plugin_registry.contract.IVersionedContent | None:
        gl = self._getGL(url)
        url_parsed = urllib.parse.urlparse(url)

        match = re.match(
            r"/(?P<project_id>.+)/-/blob/(?P<ref>[^/]+)/(?P<file_path>.+)",
            url_parsed.path,
        )
        project_id = match.group("project_id")
        file_path = match.group("file_path")
        ref = match.group("ref")
        project = self._getAndCacheProject(gl=gl, project_id=project_id)

        match = re.match(
            # Example:
            # ${environment('production').last_deployment.sha}
            # ${environment("production").last_deployment.sha}
            r"\${environment\([\"'](?P<environment_name>[^\"']+)[\"']\).last_deployment.sha}",
            ref,
        )
        environment_name = None
        if match:
            environment_name = match.group("environment_name")

        try:
            if url_parsed.path not in self._repository_content_cache:
                if environment_name:
                    environment = self._getAndCacheProjectEnvironment(
                        project=project,
                        project_id=project_id,
                        environment_name=environment_name,
                    )
                    ref = environment.last_deployment["sha"]

                self._repository_content_cache[url_parsed.path] = project.files.get(
                    file_path=file_path, ref=ref
                )

            gitlab_file = self._repository_content_cache[url_parsed.path]
            all_lines = gitlab_file.decode()

            m = re.match(r"L(?P<from>\d+)(-(?P<to>\d+))?", url_parsed.fragment)
            from_line: int = int(m.group("from"))
            to_line: int = int(m.group("to")) if m.group("to") else None
            lines = all_lines.split(b"\n")[
                from_line - 1 : to_line if to_line else from_line
            ]

            return plugin_registry.contract.IVersionedContent(
                content=b"\n".join(lines),
                last_commit_id=gitlab_file.last_commit_id[0:8],
            )

        except gitlab.GitlabGetError as e:
            self._logger.warning(f"{e.error_message}: {url}")
            return None
