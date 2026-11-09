# AkagiPlus local transport patch

Based on hudsucker 0.24.0 from crates.io, upstream https://github.com/omjadas/hudsucker.
Original MIT / Apache-2.0 licenses are retained. AkagiPlus additions, 2026:
optional loopback HTTP CONNECT transport for WebSocket/WSS and raw TCP tunnels, passed through the
builder into each connection. Default None preserves upstream behavior. HTTP uses
the same bounded CONNECT helper through AkagiPlus's custom connector.
No registry cache is modified. No RiichiCityUnlock binary or source is bundled.
