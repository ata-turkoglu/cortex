from app.ingestion.chunking import chunk_markdown


def test_chunking_preserves_heading_and_neighbor_order():
    chunks = chunk_markdown("# Başlık\n\nBir iki üç.\n\nDört beş altı.", token_limit=4, overlap=1)
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].heading == "Başlık"
    assert chunks[1].content.startswith(chunks[0].content.split()[-1])
