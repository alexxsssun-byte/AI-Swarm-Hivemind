def get_social_media_updates(target: str, platform: str) -> str:
    """
    Searches recent social media posts, news, and updates for a specific target (e.g., 'Donald Trump').
    Platforms supported: 'twitter' (or X), 'truth_social', or 'all'.
    Use this to gauge social sentiment, find recent announcements, or react to breaking news from social media.
    """
    try:
        from duckduckgo_search import DDGS
        query = target
        if platform.lower() in ['twitter', 'x']:
            query += " site:twitter.com OR site:x.com"
        elif platform.lower() in ['truth_social', 'truthsocial', 'truth']:
            query += " site:truthsocial.com"
        else:
            query += " (site:twitter.com OR site:x.com OR site:truthsocial.com)"
            
        results = ""
        with DDGS() as ddgs:
            # We use timelimit='w' to get recent posts
            for r in ddgs.text(query, timelimit='w', max_results=10):
                title = r.get('title', '')
                href = r.get('href', '')
                body = r.get('body', '')
                results += f"Source/Title: {title}\nURL: {href}\nSnippet: {body}\n\n"
                
        if not results:
            return f"No recent social media updates found for '{target}' on platform '{platform}'."
            
        return results
    except Exception as e:
        return f"Error fetching social media updates: {str(e)}"

def get_social_media_tools():
    """Returns the list of social media tools available."""
    return [get_social_media_updates]
