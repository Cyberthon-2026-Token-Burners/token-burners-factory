---
skill_id: python_rag
type: domain
triggers: [rag, weaviate, vector, embedding, retrieval, vector_db, semantic_search]
nodes: [techlead, developer, reviewer]
---
LANGUAGE TARGET: Python — RAG pipeline rules using Weaviate and Google text-embedding-004.

## Client Initialisation
- Connect via `weaviate.connect_to_weaviate_cloud` (WCS) or `weaviate.connect_to_local` for
  self-hosted, driven by environment variables:
  - `WEAVIATE_URL` — full cluster URL (default `"http://localhost:8080"`)
  - `WEAVIATE_API_KEY` — WCS API key (default `""`, omit auth header when empty)
- Wrap the client in a context manager or call `.close()` in a `finally` block; never leak the
  connection.
- Import from `weaviate` (v4 client: `pip install weaviate-client>=4`).

## Embedding
- Use `google.generativeai` with model `"models/text-embedding-004"` (768-dim, task-type aware):
  ```python
  import google.generativeai as genai
  genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
  result = genai.embed_content(
      model="models/text-embedding-004",
      content=text,
      task_type="retrieval_document",   # or "retrieval_query"
  )
  vector = result["embedding"]
  ```
- Use `task_type="retrieval_document"` for ingest; `task_type="retrieval_query"` for queries.
- Never cache raw vectors in application memory across requests — re-embed on demand or store in
  Weaviate.

## Schema
- Create the collection once at application startup (idempotent guard: check existence first):
  ```python
  if not client.collections.exists("Document"):
      client.collections.create(
          "Document",
          vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
          properties=[
              weaviate.classes.config.Property(name="text", data_type=weaviate.classes.config.DataType.TEXT),
              weaviate.classes.config.Property(name="source", data_type=weaviate.classes.config.DataType.TEXT),
          ],
      )
  ```
- Use `vectorizer_config=Configure.Vectorizer.none()` — vectors are provided externally.

## Ingest Pipeline
1. Chunk documents (max 512 tokens, 50-token overlap recommended).
2. Embed each chunk (`task_type="retrieval_document"`).
3. Batch-upsert using `client.collections.get("Document").data.insert_many(objects)`.
4. Handle `weaviate.exceptions.WeaviateInsertManyAllFailedError` — log and raise.

## Retrieval Pipeline
1. Embed query vector (`task_type="retrieval_query"`).
2. Query with `near_vector`:
   ```python
   collection = client.collections.get("Document")
   results = collection.query.near_vector(
       near_vector=query_vector,
       limit=5,
       return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
   )
   ```
3. Map `results.objects` → list of `{"text": o.properties["text"], "distance": o.metadata.distance}`.

## Grounded-Response Contract
- If `results.objects` is empty (or all distances > 0.4), the answer MUST be:
  `"No relevant context found in the knowledge base."`
- Never fabricate an answer when retrieval returns nothing.
- Pass retrieved context as a numbered list to the downstream LLM prompt; do NOT include raw
  vectors or metadata IDs in the LLM context window.

## Security
- `WEAVIATE_API_KEY` and `GEMINI_API_KEY` must never be logged or included in exception messages.
- Validate user-supplied query strings: strip leading/trailing whitespace; reject empty strings
  with a `ValueError("Query must not be empty")`.

## Test Pattern
- Mock the Weaviate client at the module level (do not connect to a live cluster in unit tests):
  ```python
  from unittest.mock import MagicMock, patch

  @patch("myapp.rag.weaviate.connect_to_weaviate_cloud")
  def test_retrieval_no_results(mock_connect):
      mock_client = MagicMock()
      mock_connect.return_value.__enter__ = lambda s: mock_client
      mock_connect.return_value.__exit__ = MagicMock(return_value=False)
      mock_client.collections.get.return_value.query.near_vector.return_value.objects = []
      # assert grounded fallback response
  ```
- Mock `google.generativeai.embed_content` to return a fixed 768-dim vector:
  `patch("google.generativeai.embed_content", return_value={"embedding": [0.0] * 768})`.
