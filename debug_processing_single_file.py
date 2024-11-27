import lib
import plugin_registry

import argparse
import logging
import difflib


def __description() -> str:
    return "Process a single XML file, entity or relationship, in coArchi format."


def __init_cli() -> argparse:
    parser = argparse.ArgumentParser(description=__description())  # , usage=__usage())
    parser.add_argument(
        "file",
        help="Path and name of the file.",
    )

    parser.add_argument(
        "-l",
        "--log",
        default="INFO",
        help="""
        Specify log level which should use. Default will always be INFO, choose between the following options
        CRITICAL, ERROR, WARNING, INFO, DEBUG
        """,
    )

    return parser


def main():

    __cli_args = __init_cli().parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname).1s %(message)s", level=__cli_args.log
    )
    logger = logging.getLogger("app")

    plugins = plugin_registry.Registry(
        plugin_directory="plugins", logger=logger
    ).loadPlugins()
    plugins = [P(logger) for P in plugins]

    in_file_name = __cli_args.file
    out_file_name = "processed.xml"

    changes_detected = lib.processFile(logger, plugins, in_file_name, out_file_name)
    print("Changes detected:", changes_detected)
    if changes_detected:
        diff = difflib.Differ().compare(
            open(in_file_name, "r").readlines(), open(out_file_name, "r").readlines()
        )
        print(''.join(diff))


if __name__ == "__main__":  # pragma: no cover
    main()
