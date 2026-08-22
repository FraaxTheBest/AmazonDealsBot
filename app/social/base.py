from dataclasses import dataclass, field


@dataclass(slots=True)
class SocialPost:
    title: str = ""
    description: str = ""
    link: str = ""
    image_url: str = ""
    hashtags: str = ""

    def text(self, *, include_link: bool = True, include_hashtags: bool = True) -> str:
        parts: list[str] = []
        if self.title.strip():
            parts.append(self.title.strip())
        if self.description.strip():
            parts.append(self.description.strip())
        if include_link and self.link.strip():
            parts.append(self.link.strip())
        if include_hashtags and self.hashtags.strip():
            parts.append(self.hashtags.strip())
        return "\n\n".join(parts).strip()


@dataclass(slots=True)
class PublishResult:
    platform: str
    success: bool
    external_id: str | None = None
    message: str = ""
    raw: dict = field(default_factory=dict)
