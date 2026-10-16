"""Where the bot should sit in voice: with the people, never alone.

Channels are given as (channel id, number of humans in it). Pure, so it is easy to test.
"""


def choose_channel(
    current: int | None,
    channels: dict[int, int],
    joined: int | None = None,
) -> int | None:
    """The voice channel the bot should be in (None = disconnect).

    - It stays where it is while someone is still there.
    - If it is alone (or not connected), it goes where somebody just joined, otherwise to the
      busiest channel; with nobody anywhere it leaves.
    """
    if current is not None and channels.get(current, 0) > 0:
        return current
    if joined is not None and channels.get(joined, 0) > 0:
        return joined
    busy = [(count, -cid) for cid, count in channels.items() if count > 0]
    if not busy:
        return None
    return -max(busy)[1]
