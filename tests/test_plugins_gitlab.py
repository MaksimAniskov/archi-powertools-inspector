import plugin_registry
import gitlab
import git
import gitdb
import logging
from test_plugin_registry import plugins
import os
from unittest import mock
import pytest
import mock


@pytest.fixture
def url_resolver(plugins):
    res = plugin_registry.getUrlResolver(plugins=plugins, scheme="gitlab")
    res._gls = (
        {}
    )  # Clear the resolver's cache of GitLab objects. Otherwise subsequent tests will use the first test's GitLab mock object.
    res._repository_compare_cache = (
        {}
    )  # Clear the resolver's cache of repository_compare return objects.
    res._repository_content_cache = {}
    res._projects_cache = {}
    res._environments_cache = {}
    res._git_fetched_for = {}
    return res


@pytest.fixture
def diff_result():
    d1 = mock.MagicMock()
    d1.a_path = "some/path/file0.txt"
    d1.b_path = None
    d1.diff = b"""@@ -1,2 +1,2 @@
 file0 line1
 line2
"""
    d2 = mock.MagicMock()
    d2.a_path = "some/path/file1.txt"
    d2.b_path = None
    d2.diff = b"""@@ -2,8 +3,7 @@ line1
 line2
 line3
 line4
+inserted line1
 line5
-line6
+line6 changed
-line7
-line8
 line9
@@ -20,5 +20,6 @@
 line20
 line21 @@ -20,5 +21,6 @@ control symbols in file's content
 line22
+inserted line2
 line23
 line24
"""

    return [d1, d2]


@mock.patch("gitlab.Gitlab")
@mock.patch.dict(
    os.environ,
    {"GITLAB_TOKEN": "gitlabfaketoken", "GITLAB_REPO_CACHE_DIR": "./gitlab_repo_cache"},
    clear=True,
)
class TestGitLabPluginCloneFetch:

    def test_git_clone(
        self,
        gl,
        url_resolver,
    ):
        with mock.patch("git.Repo.__init__") as git_repo_init, mock.patch(
            "git.Repo.clone_from"
        ) as git_repo_clone_from:
            git_repo_init.side_effect = git.exc.NoSuchPathError()
            url_resolver.diff(
                "gitlab://mygitlab.io/user/project/-/blob/main/src1.txt@a1b2c3d4#L1"
            )
            git_repo_clone_from.assert_called_once_with(
                url="https://oauth2:gitlabfaketoken@mygitlab.io/user/project.git",
                to_path="./gitlab_repo_cache/mygitlab.io/user/project",
                branch="main",
            )

    def test_git_fetch(
        self,
        gl,
        url_resolver,
    ):
        with mock.patch("git.Repo.__new__") as git_repo:
            git_repo.return_value.git.fetch.return_value = None
            url_resolver.diff(
                "gitlab://mygitlab.io/user/project/-/blob/main/src1.txt@a1b2c3d4#L1"
            )
            git_repo.return_value.git.fetch.assert_called_once_with(
                "https://oauth2:gitlabfaketoken@mygitlab.io/user/project.git",
                "refs/heads/main",
            )

    def test_git_fetch_tag(
        self,
        gl,
        url_resolver,
    ):
        def mocked_fetch(remote, ref):
            if ref == "refs/heads/tagA":
                raise git.exc.GitCommandError("dummy")
            else:
                return None

        with mock.patch("git.Repo.__new__") as git_repo:
            git_repo.return_value.git.fetch = mock.MagicMock(side_effect=mocked_fetch)
            url_resolver.diff(
                "gitlab://mygitlab.io/user/project/-/blob/tagA/src1.txt@a1b2c3d4#L1"
            )
            git_repo.return_value.git.fetch.assert_has_calls(
                [
                    mock.call(
                        "https://oauth2:gitlabfaketoken@mygitlab.io/user/project.git",
                        "refs/heads/tagA",
                    ),
                    mock.call(
                        "https://oauth2:gitlabfaketoken@mygitlab.io/user/project.git",
                        "+refs/tags/tagA:refs/tags/tagA",
                    ),
                ]
            )

    def test_diff_Exception(self, gl, url_resolver):
        with mock.patch("git.Repo.__new__") as git_repo:
            git_repo.return_value.git.fetch.side_effect = git.exc.GitCommandError(
                "dummy"
            )
            diff = url_resolver.diff(
                "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1"
            )
            assert diff == None

    def test_diff_caching_Exception(self, gl, plugins, url_resolver):
        url_resolver = plugin_registry.getUrlResolver(plugins=plugins, scheme="gitlab")
        url_resolver._gls = (
            {}
        )  # Clear the resolver's cache of GitLab objects. Otherwise subsequent tests will use the first test's GitLab mock object.
        url_resolver._repository_compare_cache = (
            {}
        )  # Clear the resolver's cache of repository_compare return objects.

        with mock.patch("git.Repo.__new__") as git_repo:
            git_repo.return_value.git.fetch.side_effect = git.exc.GitCommandError(
                "dummy"
            )

            diff1 = url_resolver.diff(
                "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6"
            )
            diff2 = url_resolver.diff(
                "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L7"
            )
            gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
            gl.return_value.projects.get.assert_called_once_with("user/project")
            assert 2 == git_repo.return_value.git.fetch.call_count
            git_repo.return_value.git.fetch.assert_has_calls(
                [
                    mock.call(
                        "https://oauth2:gitlabfaketoken@mygitlab.io/user/project.git",
                        "refs/heads/main",
                    ),
                    mock.call(
                        "https://oauth2:gitlabfaketoken@mygitlab.io/user/project.git",
                        "+refs/tags/main:refs/tags/main",
                    ),
                ]
            )
            assert diff1 == None
            assert diff2 == None


@mock.patch("gitlab.Gitlab")
@mock.patch("git.Repo.__new__")
@mock.patch.dict(
    os.environ,
    {"GITLAB_TOKEN": "gitlabfaketoken", "GITLAB_REPO_CACHE_DIR": "./gitlab_repo_cache"},
    clear=True,
)
class TestGitLabPlugin:

    def test_move(self, git, gl, url_resolver):

        d = mock.MagicMock()
        d.a_path = "some/path/move_me.txt"
        d.b_path = "another_path/new_me.txt"
        d.diff = b"""@@ -2,3 +2,3 @@line1
-line2
+line2 changed
 line3
"""
        git.return_value.commit.return_value.diff.return_value = [d]
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/move_me.txt@4306cff2#L2"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/another_path/new_me.txt@9f8e7d6c#L2"
        )
        assert diff.was_lines_content == "line2"
        assert diff.current_lines_content == "line2 changed"

    def test_diff(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-3"
        )

        # TODO: Optimize implementation to avoid this call
        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        # TODO: Optimize implementation to avoid this call
        gl.return_value.projects.get.assert_called_once_with("user/project")
        git.return_value.git.fetch.assert_called_once_with(
            "https://oauth2:gitlabfaketoken@mygitlab.io/user/project.git",
            "refs/heads/main",
        )
        git.return_value.commit.assert_has_calls(
            [
                mock.call("remotes/origin/main"),
                mock.call("a1b2c3d4"),
            ]
        )
        git.return_value.commit.return_value.diff.assert_called_once_with(
            git.return_value.commit.return_value,
            create_patch=True,
            minimal=True,
            find_renames="40%",
        )

    def test_diff01(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1"
        )
        assert diff == False

    def test_diff02(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3"
        )
        assert diff.current_lines_content == "line2"

    def test_diff03(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L4"
        )
        assert diff.current_lines_content == "line3"

    def test_diff04(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L4"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5"
        )
        assert diff.current_lines_content == "line4"

    def test_diff05(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L5"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7"
        )
        assert diff.current_lines_content == "line5"

    def test_diff06(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L8"
        )
        assert diff.was_lines_content == "line6"
        assert diff.current_lines_content == "line6 changed"

    def test_diff07(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L7"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7<-lines deleted"
        )
        assert diff.was_lines_content == "line7"
        assert diff.current_lines_content == ""

    def test_diff08(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L8"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L8<-lines deleted"
        )
        assert diff.was_lines_content == "line8"
        assert diff.current_lines_content == ""

    def test_diff09(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L9"
        )
        assert diff == False

    def test_diff10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L10"
        )
        assert diff == False

    def test_diff19(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L19"
        )
        assert diff == False

    def test_diff20(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L20"
        )
        assert diff == False

    def test_diff21(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L21"
        )
        assert diff == False

    def test_diff22(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L22"
        )
        assert diff == False

    def test_diff23(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L23"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L24"
        )
        assert diff.current_lines_content == "line23"

    def test_diff24(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L24"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L25"
        )
        assert diff.current_lines_content == "line24"

    def test_diff25(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L25"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L26"
        )
        assert diff.current_lines_content == None

    def test_diff1_2(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-2"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-3"
        )
        assert diff.current_lines_content == "line2"

    def test_diff1_3(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-3"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-4"
        )
        assert diff.current_lines_content == "line2\nline3"

    def test_diff1_4(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-4"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-5"
        )
        assert diff.current_lines_content == "line2\nline3\nline4"

    def test_diff1_5(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-5"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-7"
        )
        assert diff.was_lines_content == "line2\nline3\nline4\nline5"
        assert (
            diff.current_lines_content == "line2\nline3\nline4\ninserted line1\nline5"
        )

    def test_diff1_6(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-6"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-8"
        )
        assert diff.was_lines_content == "line2\nline3\nline4\nline5\nline6"
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff1_7(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-7"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-8"
        )
        assert diff.was_lines_content == "line2\nline3\nline4\nline5\nline6\nline7"
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff1_8(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-8"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-8"
        )
        assert (
            diff.was_lines_content == "line2\nline3\nline4\nline5\nline6\nline7\nline8"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff1_9(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-9"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-9"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff1_10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-10"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-10"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff1_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-11"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-11"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff2_3(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-3"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-4"
        )
        assert diff.current_lines_content == "line2\nline3"

    def test_diff2_4(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-4"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-5"
        )
        assert diff.current_lines_content == "line2\nline3\nline4"

    def test_diff2_5(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-5"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-7"
        )
        assert diff.was_lines_content == "line2\nline3\nline4\nline5"
        assert (
            diff.current_lines_content == "line2\nline3\nline4\ninserted line1\nline5"
        )

    def test_diff2_6(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-6"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-8"
        )
        assert diff.was_lines_content == "line2\nline3\nline4\nline5\nline6"
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff2_7(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-7"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-8"
        )
        assert diff.was_lines_content == "line2\nline3\nline4\nline5\nline6\nline7"
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff2_8(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-8"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-8"
        )
        assert (
            diff.was_lines_content == "line2\nline3\nline4\nline5\nline6\nline7\nline8"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff2_9(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-9"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-9"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff2_10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-10"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-10"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff2_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-11"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-11"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff3_4(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3-4"
        )
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L4-5"
        )
        assert diff.current_lines_content == "line3\nline4"

    def test_diff3_5(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3-5"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L4-7"
        )
        assert diff.was_lines_content == "line3\nline4\nline5"
        assert diff.current_lines_content == "line3\nline4\ninserted line1\nline5"

    def test_diff3_6(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3-6"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L4-8"
        )
        assert diff.was_lines_content == "line3\nline4\nline5\nline6"
        assert (
            diff.current_lines_content
            == "line3\nline4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff3_7(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3-7"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L4-8"
        )
        assert diff.was_lines_content == "line3\nline4\nline5\nline6\nline7"
        assert (
            diff.current_lines_content
            == "line3\nline4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff3_8(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3-8"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L4-8"
        )
        assert diff.was_lines_content == "line3\nline4\nline5\nline6\nline7\nline8"
        assert (
            diff.current_lines_content
            == "line3\nline4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff3_9(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3-9"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L4-9"
        )
        assert (
            diff.was_lines_content == "line3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff3_10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3-10"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L4-10"
        )
        assert (
            diff.was_lines_content == "line3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff3_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3-11"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L4-11"
        )
        assert (
            diff.was_lines_content == "line3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff4_5(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L4-5"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5-7"
        )
        assert diff.was_lines_content == "line4\nline5"
        assert diff.current_lines_content == "line4\ninserted line1\nline5"

    def test_diff4_6(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L4-6"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5-8"
        )
        assert diff.was_lines_content == "line4\nline5\nline6"
        assert (
            diff.current_lines_content == "line4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff4_7(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L4-7"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5-8"
        )
        assert diff.was_lines_content == "line4\nline5\nline6\nline7"
        assert (
            diff.current_lines_content == "line4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff4_8(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L4-8"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5-8"
        )
        assert diff.was_lines_content == "line4\nline5\nline6\nline7\nline8"
        assert (
            diff.current_lines_content == "line4\ninserted line1\nline5\nline6 changed"
        )

    def test_diff4_9(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L4-9"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5-9"
        )
        assert diff.was_lines_content == "line4\nline5\nline6\nline7\nline8\nline9"
        assert (
            diff.current_lines_content
            == "line4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff4_10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L4-10"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5-10"
        )
        assert diff.was_lines_content == "line4\nline5\nline6\nline7\nline8\nline9"
        assert (
            diff.current_lines_content
            == "line4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff4_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L4-11"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5-11"
        )
        assert diff.was_lines_content == "line4\nline5\nline6\nline7\nline8\nline9"
        assert (
            diff.current_lines_content
            == "line4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff5_6(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L5-6"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7-8"
        )
        assert diff.was_lines_content == "line5\nline6"
        assert diff.current_lines_content == "line5\nline6 changed"

    def test_diff5_7(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L5-7"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7-8"
        )
        assert diff.was_lines_content == "line5\nline6\nline7"
        assert diff.current_lines_content == "line5\nline6 changed"

    def test_diff5_8(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L5-8"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7-8"
        )
        assert diff.was_lines_content == "line5\nline6\nline7\nline8"
        assert diff.current_lines_content == "line5\nline6 changed"

    def test_diff5_9(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L5-9"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7-9"
        )
        assert diff.was_lines_content == "line5\nline6\nline7\nline8\nline9"
        assert diff.current_lines_content == "line5\nline6 changed\nline9"

    def test_diff5_10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L5-10"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7-10"
        )
        assert diff.was_lines_content == "line5\nline6\nline7\nline8\nline9"
        assert diff.current_lines_content == "line5\nline6 changed\nline9"

    def test_diff5_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L5-11"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7-11"
        )
        assert diff.was_lines_content == "line5\nline6\nline7\nline8\nline9"
        assert diff.current_lines_content == "line5\nline6 changed\nline9"

    def test_diff6_7(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6-7"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L8"
        )
        assert diff.was_lines_content == "line6\nline7"
        assert diff.current_lines_content == "line6 changed"

    def test_diff6_8(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6-8"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L8"
        )
        assert diff.was_lines_content == "line6\nline7\nline8"
        assert diff.current_lines_content == "line6 changed"

    def test_diff6_9(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6-9"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L8-9"
        )
        assert diff.was_lines_content == "line6\nline7\nline8\nline9"
        assert diff.current_lines_content == "line6 changed\nline9"

    def test_diff6_10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6-10"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L8-10"
        )
        assert diff.was_lines_content == "line6\nline7\nline8\nline9"
        assert diff.current_lines_content == "line6 changed\nline9"

    def test_diff6_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6-11"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L8-11"
        )
        assert diff.was_lines_content == "line6\nline7\nline8\nline9"
        assert diff.current_lines_content == "line6 changed\nline9"

    def test_diff7_8(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L7-8"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7-8<-lines deleted"
        )
        assert diff.was_lines_content == "line7\nline8"
        assert diff.current_lines_content == ""

    def test_diff7_9(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L7-9"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L9"
        )
        assert diff.was_lines_content == "line7\nline8\nline9"
        assert diff.current_lines_content == "line9"

    def test_diff7_10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L7-10"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L9-10"
        )
        assert diff.was_lines_content == "line7\nline8\nline9"
        assert diff.current_lines_content == "line9"

    def test_diff7_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L7-11"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L9-11"
        )
        assert diff.was_lines_content == "line7\nline8\nline9"
        assert diff.current_lines_content == "line9"

    def test_diff8_9(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L8-9"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L9"
        )
        assert diff.was_lines_content == "line8\nline9"
        assert diff.current_lines_content == "line9"

    def test_diff8_10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L8-10"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L9-10"
        )
        assert diff.was_lines_content == "line8\nline9"
        assert diff.current_lines_content == "line9"

    def test_diff8_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L8-11"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L9-11"
        )
        assert diff.was_lines_content == "line8\nline9"
        assert diff.current_lines_content == "line9"

    def test_diff9_10(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L9-10"
        )
        assert diff == False

    def test_diff9_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L9-11"
        )
        assert diff == False

    def test_diff10_11(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L10-11"
        )
        assert diff == False

    def test_diff_cross_chunk(self, git, gl, url_resolver):
        d = mock.MagicMock()
        d.a_path = "some/path/file1.txt"
        d.b_path = None
        d.diff = b"""@@ -2,3 +2,3 @@
 line2
 line3
 line4
@@ -20,3 +20,3 @@
 line20
 line21
 line22
"""
        git.return_value.commit.return_value.diff.return_value = [d]
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L3-21"
        )
        assert diff == False

    def test_diff_cross_chunk_1_19(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-19"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-19"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff_cross_chunk_1_20(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-20"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-20"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9...line20"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9...line20"
        )

    def test_diff_cross_chunk_1_24(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-24"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-25"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\nline23\nline24"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\ninserted line2\nline23\nline24"
        )

    def test_diff_cross_chunk_1_25(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1-25"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L1-26"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\nline23\nline24"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\ninserted line2\nline23\nline24"
        )

    def test_diff_cross_chunk_2_19(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-19"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-19"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9"
        )

    def test_diff_cross_chunk_2_20(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-20"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-20"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9...line20"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9...line20"
        )

    def test_diff_cross_chunk_2_24(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-24"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-25"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\nline23\nline24"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\ninserted line2\nline23\nline24"
        )

    def test_diff_cross_chunk_2_25(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2-25"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3-26"
        )
        assert (
            diff.was_lines_content
            == "line2\nline3\nline4\nline5\nline6\nline7\nline8\nline9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\nline23\nline24"
        )
        assert (
            diff.current_lines_content
            == "line2\nline3\nline4\ninserted line1\nline5\nline6 changed\nline9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\ninserted line2\nline23\nline24"
        )

    def test_diff_cross_chunk_9_19(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L9-19"
        )
        assert diff == False

    def test_diff_cross_chunk_9_20(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L9-20"
        )
        assert diff == False

    def test_diff_cross_chunk_9_24(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L9-24"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L9-25"
        )
        assert (
            diff.was_lines_content
            == "line9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\nline23\nline24"
        )
        assert (
            diff.current_lines_content
            == "line9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\ninserted line2\nline23\nline24"
        )

    def test_diff_cross_chunk_9_25(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L9-25"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L9-26"
        )
        assert (
            diff.was_lines_content
            == "line9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\nline23\nline24"
        )
        assert (
            diff.current_lines_content
            == "line9...line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\ninserted line2\nline23\nline24"
        )

    def test_diff_cross_chunk_10_19(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L10-19"
        )
        assert diff == False

    def test_diff_cross_chunk_10_20(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L10-20"
        )
        assert diff == False

    def test_diff_cross_chunk_10_24(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L10-24"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L10-25"
        )
        assert (
            diff.was_lines_content
            == "line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\nline23\nline24"
        )
        assert (
            diff.current_lines_content
            == "line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\ninserted line2\nline23\nline24"
        )

    def test_diff_cross_chunk_10_25(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L10-25"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L10-26"
        )
        assert (
            diff.was_lines_content
            == "line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\nline23\nline24"
        )
        assert (
            diff.current_lines_content
            == "line20\nline21 @@ -20,5 +21,6 @@ control symbols in file's content\nline22\ninserted line2\nline23\nline24"
        )

    def test_diff_two_consecutive_lines1(self, git, gl, url_resolver):
        d = mock.MagicMock()
        d.a_path = "some/path/file1.txt"
        d.b_path = None
        d.diff = b"""@@ -2,7 +2,7 @@line1
 line2
 line3
 line4
-line5
-line6
+line5 changed
+line6 changed
 line7
 line8
"""
        git.return_value.commit.return_value.diff.return_value = [d]
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L5"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5<-lines deleted"  # FIXME: It should be "#L5"
        )
        assert diff.was_lines_content == "line5"
        assert diff.current_lines_content == ""  # FIXME: It should be "line5 changed"

    def test_diff_caching(
        self,
        git,
        gl,
        plugins,
        url_resolver,
        diff_result,
    ):
        url_resolver = plugin_registry.getUrlResolver(plugins=plugins, scheme="gitlab")
        url_resolver._gls = (
            {}
        )  # Clear the resolver's cache of GitLab objects. Otherwise subsequent tests will use the first test's GitLab mock object.
        url_resolver._repository_compare_cache = (
            {}
        )  # Clear the resolver's cache of repository_compare return objects.

        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"
        diff1 = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6"
        )
        # url_resolver is expected to use the cached data during the second diff call
        diff2 = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L7"
        )
        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        gl.return_value.projects.get.assert_called_once_with("user/project")
        git.return_value.git.fetch.assert_called_once_with(
            "https://oauth2:gitlabfaketoken@mygitlab.io/user/project.git",
            "refs/heads/main",
        )
        assert type(diff1) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff1.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L8"
        )
        assert diff1.was_lines_content == "line6"
        assert diff1.current_lines_content == "line6 changed"
        assert type(diff2) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff2.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L7<-lines deleted"
        )

    def test_diff_caching2(
        self,
        git,
        gl,
        plugins,
        url_resolver,
        diff_result,
    ):
        url_resolver = plugin_registry.getUrlResolver(plugins=plugins, scheme="gitlab")
        url_resolver._gls = (
            {}
        )  # Clear the resolver's cache of GitLab objects. Otherwise subsequent tests will use the first test's GitLab mock object.
        url_resolver._repository_compare_cache = (
            {}
        )  # Clear the resolver's cache of repository_compare return objects.

        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff1 = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6"
        )
        # url_resolver is expected to use the cached data during the second diff call
        diff2 = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file2.txt@a1b2c3d4#L7"
        )

        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        gl.return_value.projects.get.assert_called_once_with("user/project")
        git.return_value.git.fetch.assert_called_once_with(
            "https://oauth2:gitlabfaketoken@mygitlab.io/user/project.git",
            "refs/heads/main",
        )

        assert type(diff1) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff1.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L8"
        )
        assert diff1.was_lines_content == "line6"
        assert diff1.current_lines_content == "line6 changed"

        assert diff2 == False

    def test_diff_two_consecutive_lines2(self, git, gl, url_resolver):
        d = mock.MagicMock()
        d.a_path = "some/path/file1.txt"
        d.b_path = None
        d.diff = b"""@@ -2,7 +2,7 @@line1
 line2
 line3
 line4
-line5
-line6
+line5 changed
+line6 changed
 line7
 line8
"""
        git.return_value.commit.return_value.diff.return_value = [d]
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L6"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5-6"  # FIXME: It should be "#L6"
        )
        assert diff.was_lines_content == "line6"
        assert (
            diff.current_lines_content == "line5 changed\nline6 changed"
        )  # FIXME: It should be "line6 changed"

    def test_diff_two_consecutive_lines3(self, git, gl, url_resolver):
        d = mock.MagicMock()
        d.a_path = "some/path/file1.txt"
        d.b_path = None
        d.diff = b"""@@ -2,7 +2,7 @@line1
 line2
 line3
 line4
-line5
-line6
+line5 changed
+line6 changed
 line7
 line8
"""
        git.return_value.commit.return_value.diff.return_value = [d]
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L5-6"
        )
        assert type(diff) == plugin_registry.contract.IDiffContentChanged
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L5-6"
        )
        assert diff.was_lines_content == "line5\nline6"
        assert diff.current_lines_content == "line5 changed\nline6 changed"

    def test_diff_empty_diffs(self, git, gl, url_resolver):
        git.return_value.commit.return_value.diff.return_value = []
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L1"
        )
        assert diff == False

    def test_diff_malformed_url_fragment(
        self,
        git,
        gl,
        url_resolver,
        diff_result,
    ):
        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@a1b2c3d4#L2<-lines deleted"
        )
        # Non-numeric symbols terminating line number sequence get ignored.
        assert type(diff) == plugin_registry.contract.IDiffLinesMoved
        assert (
            diff.updated_url
            == "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt@9f8e7d6c#L3"
        )
        assert diff.current_lines_content == "line2"

    def test_resolveToContent(self, git, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent\nline2\nline3"
        )
        gl.return_value.projects.get.return_value.files.get.return_value.last_commit_id = (
            "a1b2c3d4e5f6"
        )

        content_obj = url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L2"
        )

        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        gl.return_value.projects.get.return_value.files.get.assert_called_once_with(
            file_path="some/path/file1.txt", ref="main"
        )
        assert content_obj.content == b"line2"
        assert content_obj.last_commit_id == "a1b2c3d4"

    def test_resolveToContent_Multiline(self, git, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent\nline2\nline3\nline4"
        )
        gl.return_value.projects.get.return_value.files.get.return_value.last_commit_id = (
            "a1b2c3d4e5f6"
        )

        content_obj = url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L2-3"
        )

        gl.return_value.projects.get.return_value.files.get.assert_called_once_with(
            file_path="some/path/file1.txt", ref="main"
        )

        assert content_obj.content == b"line2\nline3"
        assert content_obj.last_commit_id == "a1b2c3d4"

    def test_resolveToContent_Exception(self, git, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.side_effect = (
            gitlab.GitlabGetError("Test")
        )

        content = url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L1"
        )
        assert content == None

    def test_resolveToContent_Cache(self, git, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent"
        )

        url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L1"
        )
        url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L1"
        )

        assert gl.call_count == 1  # Not 2

    def test_resolveToContent_EnableDebug(self, git, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent"
        )

        logging.getLogger("tests").setLevel("DEBUG")
        url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L1"
        )

        gl.return_value.enable_debug.assert_called()

    def test_diff_environment_last_deployment(self, git, gl, url_resolver, diff_result):
        env0 = mock.MagicMock(id="123")
        env0.name = "some_name_1"
        env1 = mock.MagicMock(id="456")
        env1.name = "production"
        env2 = mock.MagicMock(id="789")
        env2.name = "some_name_2"
        gl.return_value.projects.get.return_value.environments.list.return_value = [
            env0,
            env1,
            env2,
        ]

        d = {}
        d["ref"] = "main"
        gl.return_value.projects.get.return_value.environments.get.return_value = (
            mock.MagicMock(last_deployment=d)
        )

        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/${environment('production').last_deployment.sha}/some/path/file1.txt@a1b2c3d4#L2-3"
        )
        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        gl.return_value.projects.get.assert_called_once_with("user/project")
        gl.return_value.projects.get.return_value.environments.list.assert_called_once()
        gl.return_value.projects.get.return_value.environments.get.assert_called_once_with(
            "456"
        )
        git.return_value.commit.return_value.diff.assert_called_once_with(
            git.return_value.commit.return_value,
            create_patch=True,
            minimal=True,
            find_renames="40%",
        )

    def test_diff_environment_last_deployment_exception(
        self, git, gl, url_resolver, diff_result
    ):
        mock_commit = mock.Mock()
        mock_commit.diff.return_value = diff_result
        mock_commit.hexsha = "9f8e7d6c000000000"

        def commit_side_effect(rev):
            if rev == "remotes/origin/main":
                raise gitdb.exc.BadName
            return mock_commit

        env0 = mock.MagicMock(id="123")
        env0.name = "some_name_1"
        env1 = mock.MagicMock(id="456")
        env1.name = "production"
        env2 = mock.MagicMock(id="789")
        env2.name = "some_name_2"
        gl.return_value.projects.get.return_value.environments.list.return_value = [
            env0,
            env1,
            env2,
        ]

        d = {}
        d["ref"] = "main"
        gl.return_value.projects.get.return_value.environments.get.return_value = (
            mock.MagicMock(last_deployment=d)
        )

        git.return_value.commit.side_effect = commit_side_effect

        diff = url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/${environment('production').last_deployment.sha}/some/path/file1.txt@a1b2c3d4#L2-3"
        )
        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        gl.return_value.projects.get.assert_called_once_with("user/project")
        gl.return_value.projects.get.return_value.environments.list.assert_called_once()
        gl.return_value.projects.get.return_value.environments.get.assert_called_once_with(
            "456"
        )
        mock_commit.diff.assert_called_once_with(
            mock_commit,
            create_patch=True,
            minimal=True,
            find_renames="40%",
        )

    def test_diff_environment_last_deployment_caching(
        self, git, gl, url_resolver, diff_result
    ):
        env0 = mock.MagicMock(id="123")
        env0.name = "some_name_1"
        env1 = mock.MagicMock(id="456")
        env1.name = "production"
        env2 = mock.MagicMock(id="789")
        env2.name = "some_name_2"
        gl.return_value.projects.get.return_value.environments.list.return_value = [
            env0,
            env1,
            env2,
        ]

        d = {}
        d["sha"] = "0123456789abcdef0123456789abcdef01234567"
        gl.return_value.projects.get.return_value.environments.get.return_value = (
            mock.MagicMock(last_deployment=d)
        )

        git.return_value.commit.return_value.diff.return_value = diff_result
        git.return_value.commit.return_value.hexsha = "9f8e7d6c000000000"

        url_resolver._environments_cache = {}

        url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/${environment('production').last_deployment.sha}/some/path/file1.txt@a1b2c3d4#L2-3"
        )

        url_resolver.diff(
            "gitlab://mygitlab.io/user/project/-/blob/${environment('production').last_deployment.sha}/other/path/file2.txt@01234567#L1"
        )

        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        gl.return_value.projects.get.assert_called_once_with("user/project")
        gl.return_value.projects.get.return_value.environments.list.assert_called_once()
        gl.return_value.projects.get.return_value.environments.get.assert_called_once_with(
            "456"
        )

    def test_resolveToContent_environment_last_deployment(self, git, gl, url_resolver):
        env0 = mock.MagicMock(id="123")
        env0.name = "some_name_1"
        env1 = mock.MagicMock(id="456")
        env1.name = "production"
        env2 = mock.MagicMock(id="789")
        env2.name = "some_name_2"
        gl.return_value.projects.get.return_value.environments.list.return_value = [
            env0,
            env1,
            env2,
        ]

        d = {}
        d["sha"] = "0123456789abcdef0123456789abcdef01234567"
        gl.return_value.projects.get.return_value.environments.get.return_value = (
            mock.MagicMock(last_deployment=d)
        )

        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent\nline2\nline3"
        )
        gl.return_value.projects.get.return_value.files.get.return_value.last_commit_id = (
            "a1b2c3d4e5f6"
        )

        content_obj = url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/${environment('production').last_deployment.sha}/some/path/file1.txt#L2"
        )

        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        gl.return_value.projects.get.assert_called_once_with("user/project")
        gl.return_value.projects.get.return_value.environments.list.assert_called_once()
        gl.return_value.projects.get.return_value.environments.get.assert_called_once_with(
            "456"
        )
        gl.return_value.projects.get.return_value.files.get.assert_called_once_with(
            file_path="some/path/file1.txt",
            ref="0123456789abcdef0123456789abcdef01234567",
        )
        assert content_obj.content == b"line2"
        assert content_obj.last_commit_id == "a1b2c3d4"

    def test_resolveToContent_environment_last_deployment_caching(
        self, git, gl, url_resolver
    ):
        env0 = mock.MagicMock(id="123")
        env0.name = "some_name_1"
        env1 = mock.MagicMock(id="456")
        env1.name = "production"
        env2 = mock.MagicMock(id="789")
        env2.name = "some_name_2"
        gl.return_value.projects.get.return_value.environments.list.return_value = [
            env0,
            env1,
            env2,
        ]

        d = {}
        d["sha"] = "0123456789abcdef0123456789abcdef01234567"
        gl.return_value.projects.get.return_value.environments.get.return_value = (
            mock.MagicMock(last_deployment=d)
        )

        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent\nline2\nline3"
        )
        gl.return_value.projects.get.return_value.files.get.return_value.last_commit_id = (
            "a1b2c3d4e5f6"
        )

        url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/${environment('production').last_deployment.sha}/some/path/file1.txt#L2"
        )

        content_obj = url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/${environment('production').last_deployment.sha}/some/path/file1.txt#L2"
        )

        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        gl.return_value.projects.get.assert_called_once_with("user/project")
        gl.return_value.projects.get.return_value.environments.list.assert_called_once()
        gl.return_value.projects.get.return_value.environments.get.assert_called_once_with(
            "456"
        )
        gl.return_value.projects.get.return_value.files.get.assert_called_once_with(
            file_path="some/path/file1.txt",
            ref="0123456789abcdef0123456789abcdef01234567",
        )
        assert content_obj.content == b"line2"
        assert content_obj.last_commit_id == "a1b2c3d4"
