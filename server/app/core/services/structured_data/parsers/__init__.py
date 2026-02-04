"""Parser factory for structured data sources."""

from .base import BaseParser, ParsedRequirement
from .csv_parser import CSVParser
from .html_table_parser import HTMLTableParser


def get_parser(source_type: str) -> BaseParser:
    """
    Factory function to get the appropriate parser for a source type.

    Args:
        source_type: Type of source ('csv' or 'html_table')

    Returns:
        Parser instance for the source type

    Raises:
        ValueError: If source type is not supported
    """
    parsers = {
        "csv": CSVParser,
        "html_table": HTMLTableParser,
    }

    parser_class = parsers.get(source_type)
    if not parser_class:
        raise ValueError(f"Unsupported source type: {source_type}")

    return parser_class()


__all__ = ["get_parser", "BaseParser", "ParsedRequirement", "CSVParser", "HTMLTableParser"]
