# Release Checklist

1. Update `src/freshdocs/__init__.py` and `pyproject.toml` version.
2. Run:

   ```sh
   just ci
   ```

3. Smoke test:

   ```sh
   freshdocs init
   freshdocs sync --lib hono
   freshdocs context "middleware auth" --lib hono
   freshdocs sources --top-languages 300 --format jsonl | wc -l
   printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n' | freshdocs mcp
   ```

4. Tag:

   ```sh
   gh repo create Supersynergy/freshdocs --public --source . --remote origin --push
   git tag v0.1.0
   git push origin main --tags
   ```

5. Publish package when ready.
