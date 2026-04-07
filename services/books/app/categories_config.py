from typing import List

from pydantic import BaseModel


class SubGenreConfig(BaseModel):
    slug: str
    name: str
    keywords: List[str]
    exact_slugs: List[str] = []


class CategoryConfig(BaseModel):
    slug: str
    name: str
    keywords: List[str]
    exact_slugs: List[str] = []
    sub_genres: List[SubGenreConfig] = []


CATEGORIES = {
    "fantasy": CategoryConfig(
        slug="fantasy",
        name="Fantasy",
        keywords=[
            "fantasy",
            "magic",
            "dragons",
            "wizard",
            "witches",
            "mythology",
            "fairies",
        ],
        exact_slugs=["fantasy", "high-fantasy", "urban-fantasy", "epic-fantasy"],
        sub_genres=[
            SubGenreConfig(
                slug="high-fantasy",
                name="High Fantasy",
                keywords=["epic fantasy", "high fantasy", "sword and sorcery"],
            ),
            SubGenreConfig(
                slug="urban-fantasy",
                name="Urban Fantasy",
                keywords=["urban fantasy", "paranormal", "vampires", "werewolves"],
            ),
            SubGenreConfig(
                slug="magic",
                name="Magic",
                keywords=["magic", "witches", "wizards", "sorcery"],
            ),
        ],
    ),
    "science-fiction": CategoryConfig(
        slug="science-fiction",
        name="Science Fiction",
        keywords=[
            "science fiction",
            "sci-fi",
            "space",
            "aliens",
            "cyberpunk",
            "dystopian",
            "futuristic",
            "time travel",
        ],
        exact_slugs=["science-fiction", "sci-fi"],
        sub_genres=[
            SubGenreConfig(
                slug="space-opera",
                name="Space Opera",
                keywords=["space opera", "galactic"],
            ),
            SubGenreConfig(
                slug="cyberpunk",
                name="Cyberpunk",
                keywords=["cyberpunk", "hacker", "artificial intelligence"],
            ),
            SubGenreConfig(
                slug="dystopian",
                name="Dystopian",
                keywords=["dystopia", "post-apocalyptic"],
            ),
        ],
    ),
    "romance": CategoryConfig(
        slug="romance",
        name="Romance",
        keywords=["romance", "love", "contemporary romance", "historical romance"],
        exact_slugs=["romance", "love-story"],
        sub_genres=[
            SubGenreConfig(
                slug="contemporary-romance",
                name="Contemporary",
                keywords=["contemporary romance", "modern romance"],
            ),
            SubGenreConfig(
                slug="historical-romance",
                name="Historical Romance",
                keywords=["historical romance", "regency", "victorian romance"],
            ),
            SubGenreConfig(
                slug="romantasy",
                name="Romantasy",
                keywords=["romantic fantasy", "romantasy"],
            ),
        ],
    ),
    "mystery-thriller": CategoryConfig(
        slug="mystery-thriller",
        name="Mystery & Thriller",
        keywords=["mystery", "thriller", "suspense", "crime", "detective", "murder"],
        exact_slugs=["mystery", "thriller", "crime", "suspense"],
        sub_genres=[
            SubGenreConfig(
                slug="detective",
                name="Detective",
                keywords=["detective", "investigation", "police procedural"],
            ),
            SubGenreConfig(
                slug="psychological-thriller",
                name="Psychological Thriller",
                keywords=["psychological thriller", "mind-bending"],
            ),
            SubGenreConfig(
                slug="true-crime",
                name="True Crime",
                keywords=["true crime", "serial killer"],
            ),
        ],
    ),
    "horror": CategoryConfig(
        slug="horror",
        name="Horror",
        keywords=["horror", "scary", "ghosts", "haunted", "macabre", "supernatural"],
        exact_slugs=["horror", "supernatural-horror"],
        sub_genres=[
            SubGenreConfig(
                slug="paranormal",
                name="Paranormal",
                keywords=["paranormal", "ghosts", "haunted"],
            ),
            SubGenreConfig(
                slug="slasher", name="Slasher", keywords=["slasher", "gore", "splatter"]
            ),
        ],
    ),
    "historical-fiction": CategoryConfig(
        slug="historical-fiction",
        name="Historical Fiction",
        keywords=["historical fiction", "history", "world war", "tudor", "ancient"],
        exact_slugs=["historical-fiction", "history"],
        sub_genres=[
            SubGenreConfig(
                slug="wwii",
                name="World War II",
                keywords=["world war ii", "ww2", "holocaust"],
            ),
            SubGenreConfig(
                slug="ancient-history",
                name="Ancient History",
                keywords=["ancient rome", "ancient greece", "ancient egypt"],
            ),
        ],
    ),
    "non-fiction": CategoryConfig(
        slug="non-fiction",
        name="Non-Fiction",
        keywords=[
            "non-fiction",
            "biography",
            "memoir",
            "self-help",
            "business",
            "science",
            "psychology",
            "philosophy",
        ],
        exact_slugs=["non-fiction", "biography", "memoir", "self-help"],
        sub_genres=[
            SubGenreConfig(
                slug="biography-memoir",
                name="Biography & Memoir",
                keywords=["biography", "memoir", "autobiography"],
            ),
            SubGenreConfig(
                slug="self-help",
                name="Self-Help",
                keywords=["self-help", "personal development", "productivity"],
            ),
            SubGenreConfig(
                slug="science",
                name="Science",
                keywords=["science", "physics", "biology", "space"],
            ),
        ],
    ),
}
