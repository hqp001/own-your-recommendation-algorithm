def _matches_any(post: dict, keywords: list[str]) -> bool:
    haystack = f"{post['text']} {post['author']} {post['handle']}".lower()
    return any(kw.lower() in haystack for kw in keywords)


def filter_posts(posts: list[dict], keywords_include: list[str], keywords_exclude: list[str]) -> list[dict]:
    result = posts
    if keywords_include:
        result = [p for p in result if _matches_any(p, keywords_include)]
    if keywords_exclude:
        result = [p for p in result if not _matches_any(p, keywords_exclude)]
    return result
