"""Every mood-board bound in one place. The client mirrors these in
`client/src/cappe/boards/limits.ts`; `test_cappe_boards.py` holds the two equal."""

MAX_BOARDS_PER_SITE = 50
MAX_PINS_PER_BOARD = 300
# A site's pinned files together (a library picture pinned costs nothing: the
# library already holds it).
MAX_SITE_BYTES = 1024 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024

TITLE_MAX = 120
NOTE_MAX = 2000
URL_MAX = 2048
LINK_TITLE_MAX = 300
LINK_DESCRIPTION_MAX = 500
SITE_NAME_MAX = 120
FILENAME_MAX = 200

# A board is a plane around its origin; pins are placed in its units (CSS px at 100%).
COORD_MAX = 20000.0
SIZE_MIN = 24.0
SIZE_MAX = 4000.0
ROTATION_MAX = 180.0
Z_MAX = 1_000_000

NOTE_COLORS = ("yellow", "pink", "blue", "green", "purple", "white")
