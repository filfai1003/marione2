from dataclasses import dataclass, field

import httpx

from marione.bot.context import Services
from marione.bot.music import MusicPlayer
from marione.domain.limits import PlayLimiter
from marione.llm.catalog import ModelCatalog
from marione.ports import GuildView


@dataclass
class WebDeps:
    services: Services
    guild: GuildView
    # Set only by the local preview: that user is always logged in. Never read from the env.
    dev_user_id: int | None = None
    http: httpx.AsyncClient = field(default_factory=lambda: httpx.AsyncClient(timeout=10))
    # At most 40 changes per member per minute: a runaway script cannot flood the database.
    limiter: PlayLimiter = field(default_factory=lambda: PlayLimiter(40, 60))
    catalog: ModelCatalog | None = None
    music: MusicPlayer | None = None

    def models(self) -> ModelCatalog:
        if self.catalog is None:
            self.catalog = ModelCatalog(self.http)
        return self.catalog
