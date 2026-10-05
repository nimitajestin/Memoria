from ingestion.chunking.chunk import MAXIMUM, chunk_units
from ingestion.parsers import TextUnit


def test_small_unit_stays_one_chunk() -> None:
    drafts = chunk_units([TextUnit(text="short", section="Intro", line_start=1, line_end=1)])
    assert len(drafts) == 1
    assert drafts[0].section == "Intro"


def test_long_unit_is_split_below_the_maximum() -> None:
    text = ("Harbor chunk. " * 200).strip()
    assert len(text) > MAXIMUM
    drafts = chunk_units([TextUnit(text=text, line_start=1, line_end=40)])
    assert len(drafts) > 1
    assert all(len(item.text) <= MAXIMUM for item in drafts)
