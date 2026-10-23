"""Gummfit Studio: stories made of pages (`cappe_posts.format = 'pages'`).

A paged story is one document (`content = {"doc": {...}}`): its pages, the
frames and shapes on them, and the text that flows through its text frames
(threads), with each thread's composition — every line as the Studio set it.
The Studio (client `client/src/cappe/studio/`) measures and breaks the text;
the server never measures. It checks the document (`schema`), prints the
pages exactly as composed (`render`), and derives the story's Text view
(`text_view`), which is what the feed, emails, word counts and the iOS app
read.
"""
