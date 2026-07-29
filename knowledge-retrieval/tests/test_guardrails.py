"""守卫：retrieval lifespan 无 embedding 消费者。"""

from pathlib import Path


def test_retrieval_server_has_no_embedding_consumers():
    """允许本包 MessageStream/Broadcast；禁止挂 content 侧 embedding 消费者。"""
    retrieval_src = Path(__file__).resolve().parents[1] / 'src' / 'knowledge_retrieval'
    server = retrieval_src / 'server' / 'server.py'
    text = server.read_text(encoding='utf-8')
    assert 'embedding.pending' not in text
    assert 'knowledge_content.message' not in text
    assert "register_consumer_paths(['knowledge_retrieval.message.consumer'])" in text

    consumer_dir = retrieval_src / 'message' / 'consumer'
    consumer_files = {p.name for p in consumer_dir.glob('*.py')}
    assert 'embedding_task_consumer.py' not in consumer_files
    assert 'document_parse_consumer.py' not in consumer_files
    assert 'web_crawler_task_consumer.py' not in consumer_files
    assert 'crawl_document_consumer.py' not in consumer_files
