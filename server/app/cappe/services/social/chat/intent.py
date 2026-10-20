"""What the owner asked for, read from their own words before the model is
asked: post, prepare files to download, or both; which platforms; captions.

"prepare this for all platforms", "cut it for TikTok and YouTube", "export
versions", "make sure they have word-for-word captions" — the same reading
on every turn, whatever the model makes of it. `plan.py` decides from this
what files to make; the model only writes the words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PLATFORMS = {
    "instagram": r"instagram|insta|ig|reels?",
    "facebook": r"facebook|fb",
    "tiktok": r"tik\s*-?\s*tok",
    # Not bare "shorts": an apparel store posts those.
    "youtube": r"you\s*-?\s*tube|yt",
}
_PLATFORM_NAMES = "|".join(_PLATFORMS.values())

_PREPARE = re.compile(
    r"\b(prepare|export|downloadable|resize|re-?size|reformat"
    r"|(?:for|to) download|download (?:it|them|the (?:files?|videos?|versions?|cuts?)|versions?|files?|copies|cuts?)"
    r"|cut (?:it|this|these|them|that|those|the (?:video|clip)s?) (?:for|to|into)"
    rf"|cut (?:for|to fit) (?:{_PLATFORM_NAMES}|all|every|each)"
    rf"|(?:versions?|files?|formats?|cuts?|copies) (?:for|of it for|to post on|to upload to) (?:{_PLATFORM_NAMES}|all|every|each)"
    rf"|(?:a |the |an )?(?:{_PLATFORM_NAMES}|vertical|landscape) (?:versions?|cuts?|files?|formats?)"
    r"|i'?ll (?:post|upload) (?:it|them) (?:myself|manually|by hand)|(?:upload|post) (?:it |them )?(?:myself|manually|by hand))\b",
    re.I,
)
_POST = re.compile(r"\b(post|publish|share|schedule|put (?:it|this|these|them) (?:up|out)|go live)\b", re.I)
_ALL = re.compile(
    r"\b(all (?:the |my |our )?(?:platforms|socials|networks|channels|apps|accounts)|everywhere|every (?:platform|network|channel|app)"
    r"|all (?:three|3)|all of them)\b",
    re.I,
)
_NO_CAPTIONS = re.compile(r"\b(?:no|without|skip|drop|remove|don'?t (?:add|want|need)) (?:the |any )?"
                          r"(?:captions?|subtitles?|subs|transcripts?)\b", re.I)
_CAPTIONS = re.compile(
    r"\b(captions?|captioned|subtitles?|subtitled|subs|word[- ]for[- ]word|word by word|transcri(?:be|bed|pt|pts|ption)"
    r"|karaoke|on[- ]screen (?:text|words)|burn(?:ed)?[- ]in)\b",
    re.I,
)
# "captions" also means the post's text ("write captions for these"); only
# these say the words go on the video.
_ON_VIDEO = re.compile(r"\b(word[- ]for[- ]word|word by word|subtitles?|subtitled|subs|transcri\w*|karaoke"
                       r"|on[- ]screen|burn(?:ed)?[- ]in|on the video|in the video|closed caption)\b", re.I)


@dataclass(frozen=True)
class Ask:
    prepare: bool = False
    post: bool = False
    everywhere: bool = False
    platforms: frozenset[str] = field(default_factory=frozenset)
    captions: bool | None = None

    @property
    def files_only(self) -> bool:
        """Files to download, nothing posted."""
        return self.prepare and not self.post


def parse(text: str) -> Ask:
    words = text or ""
    platforms = frozenset(name for name, pattern in _PLATFORMS.items()
                          if re.search(rf"\b(?:{pattern})\b", words, re.I))
    captions: bool | None = None
    if _NO_CAPTIONS.search(words):
        captions = False
    elif _CAPTIONS.search(words) and (_ON_VIDEO.search(words) or _PREPARE.search(words)):
        captions = True
    prepare = bool(_PREPARE.search(words))
    post = bool(_POST.search(words))
    # "post it myself" asks for files, not a post.
    if post and re.search(r"\b(?:post|upload) (?:it |them )?(?:myself|manually|by hand)\b", words, re.I):
        post = False
    if captions and not prepare and not post:
        prepare = True  # "make sure they have word-for-word captions" is about the files
    return Ask(prepare=prepare, post=post, everywhere=bool(_ALL.search(words)), platforms=platforms,
               captions=captions)


__all__ = ["Ask", "parse"]
