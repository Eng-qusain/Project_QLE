## Project_QLE/parsers/__init__.py
from .file_parser import parse_file, detect_file_type
from .las_parser  import parse_las, las_to_parsed_file

def parse_segy(path):
    from .segy_parser import parse_segy
    return parse_segy(path)


def segy_to_parsed_file(path):
    from .segy_parser import segy_to_parsed_file
    return segy_to_parsed_file(path)

__all__ = [
    "parse_file", "detect_file_type",
    "parse_las",  "las_to_parsed_file",
    "parse_segy", "segy_to_parsed_file",
]
