// Mood-board bounds, mirroring the server's `services/boards/limits.py`
// (`server/tests/cappe/test_cappe_boards.py` holds the two equal).

export const MAX_BOARDS_PER_SITE = 50
export const MAX_PINS_PER_BOARD = 300
export const MAX_SITE_BYTES = 1024 * 1024 * 1024
export const MAX_FILE_BYTES = 25 * 1024 * 1024

export const TITLE_MAX = 120
export const NOTE_MAX = 2000
export const URL_MAX = 2048

export const COORD_MAX = 20000
export const SIZE_MIN = 24
export const SIZE_MAX = 4000
export const ROTATION_MAX = 180
export const Z_MAX = 1_000_000

export const NOTE_COLORS = ['yellow', 'pink', 'blue', 'green', 'purple', 'white'] as const
export type NoteColor = (typeof NOTE_COLORS)[number]
