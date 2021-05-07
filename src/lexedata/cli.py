from pathlib import Path
import logging
import argparse
import typing as t

import tqdm

logger = logging.getLogger("lexedata")
logging.basicConfig(level=logging.INFO)


def tq(iter, logger=logger, total: t.Optional[t.Union[int, float]] = None):
    if logger.getEffectiveLevel() >= logging.INFO:
        return tqdm.tqdm(iter, total=total)
    else:
        return iter


def add_log_controls(parser: argparse.ArgumentParser):
    logcontrol = parser.add_argument_group("Logging")
    logcontrol.add_argument("--loglevel", type=int, default=logging.INFO)
    logcontrol.add_argument(
        "-q", action="store_const", const=logging.WARNING, dest="loglevel"
    )
    logcontrol.add_argument(
        "-v", action="store_const", const=logging.DEBUG, dest="loglevel"
    )


def setup_logging(args: argparse.Namespace):
    logger.setLevel(args.loglevel)
    return logger


def parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--metadata",
        type=Path,
        default="Wordlist-metadata.json",
        help="Path to the JSON metadata file describing the dataset (default: ./Wordlist-metadata.json)",
    )
    add_log_controls(parser)
    return parser
