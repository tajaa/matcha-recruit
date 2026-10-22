// The story-block vocabulary and layouts. The server's `story_schema.py` is
// the authority; `test_cappe_story_schema.py` keeps these two lists equal.
export const STORY_BLOCKS = ['cover', 'text', 'photo', 'photos', 'quote', 'sidebar', 'qa', 'divider', 'paywall'] as const
export const STORY_LAYOUTS = ['standard', 'cover_story', 'photo_essay', 'interview', 'dispatch', 'lookbook'] as const

export type StoryBlockType = (typeof STORY_BLOCKS)[number]
export type StoryLayout = (typeof STORY_LAYOUTS)[number]
