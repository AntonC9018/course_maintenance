"""Shared patterns for course maintenance (extracted verbatim)."""

import re

# Ordered lab file: NN_rest, NN_MM_rest, or NN<letter>_rest (stem),
# e.g. 01_instruction, 21a_function_execution. A letter-suffixed file is
# treated as its own entry in sort order: on rename it takes the next free
# number and the letter is stripped (16, 16a, 17 -> 16, 17, 18).
ORDERED_PATTERN = re.compile(r'^(\d+)([a-z])?(?:_(\d+))?_(.+)$')
H1_RE = re.compile(r'^(#\s+)(\d+)(\.\s+.+)')
H3_RE = re.compile(r'^(###\s+)(\d+)(\.\s+.+)')
LIST_ITEM_RE = re.compile(r'^(\d+)[.)]\s*(.*)')
FENCE_RE = re.compile(r'^\s*(```|~~~)')
LINK_RE = re.compile(r'(!?\[[^\]]*\]\()([^)\s]+)(\s+[^)]*)?(\))')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
NUM_PREFIX_RE = re.compile(r'^\d+-')

EXTERNAL_PREFIXES = ('http://', 'https://', 'mailto:', '//', 'data:', 'ftp://')
