# AGENTS Guidelines for This Repository

This repository contains a Solana Yellowstone gRPC Geyser tutorial and examples. When working on the project interactively with an agent (e.g. the Codex CLI) please follow the guidelines below for efficient development and testing.

## 1. Use Learning Examples for Testing

* **Always test with learning examples** in `learning-examples/` before creating new monitors.
* **Start with basic filters** before implementing complex ones.
* **Monitor connection stability** when running long-term subscriptions.
* **Use `PROCESSED` commitment** for fastest updates during development.

## 2. Keep Dependencies in Sync

If you add or update dependencies:

1. Use `uv add <package>` to add new dependencies.
2. The `uv.lock` file will be automatically updated.
3. Verify compatibility with Python 3.13+ as specified in the project.

## 3. Protocol Buffer Management

When working with proto files:

* Keep proto files in sync with the official Yellowstone repository.
* After regenerating client code, fix imports in generated files:
  - In `geyser_pb2.py`: Change absolute imports to relative imports
  - In `geyser_pb2_grpc.py`: Change absolute imports to relative imports
* Never edit generated files directly except for import fixes.

## 4. Code Quality Checks

Before completing any task, run these quality checks:

| Command            | Purpose                           |
| ------------------ | --------------------------------- |
| `uv run ruff format`  | Format code to standards      |
| `uv run ruff check`   | Run linting checks             |
| `uv run ruff check --fix` | Auto-fix linting issues    |

## 5. Environment Configuration

Create a `.env` file with required credentials (never commit):

```env
GEYSER_ENDPOINT=YOUR_YELLOWSTONE_GRPC_ENDPOINT
GEYSER_API_TOKEN=YOUR_API_TOKEN
```

## 6. Testing Workflow

Test changes progressively:

1. **Connection test**: Verify gRPC connection first
   ```bash
   uv run learning-examples/slots_subscription.py
   ```

2. **Basic filters**: Test simple subscriptions
   ```bash
   uv run learning-examples/accounts_basic_filter.py
   uv run learning-examples/transactions_basic_filter.py
   ```

3. **Advanced filters**: Test complex filtering logic
   ```bash
   uv run learning-examples/accounts_advanced_filter.py
   uv run learning-examples/transactions_advanced_filter.py
   ```

4. **Main application**: Test complete implementation
   ```bash
   uv run main.py
   ```

## 7. Development Best Practices

* Use type hints for all function parameters and returns.
* Include docstrings explaining filter purposes.
* Handle connection errors gracefully with retries.
* Implement keepalive options for long-running subscriptions.
* Log important events for debugging.

## 8. Common Development Tasks

### Regenerate Proto Files
```bash
# Download latest proto files
curl -o proto/geyser.proto https://raw.githubusercontent.com/rpcpool/yellowstone-grpc/master/yellowstone-grpc-proto/proto/geyser.proto
curl -o proto/solana-storage.proto https://raw.githubusercontent.com/rpcpool/yellowstone-grpc/master/yellowstone-grpc-proto/proto/solana-storage.proto

# Generate Python code
uv run --with grpcio-tools -- python -m grpc_tools.protoc \
    --python_out=./generated \
    --grpc_python_out=./generated \
    --proto_path=./proto \
    geyser.proto solana-storage.proto

# Fix imports manually in generated files
```

### Add New Learning Example
1. Create new file in `learning-examples/`
2. Follow existing patterns for connection and subscription setup
3. Document the specific use case in comments
4. Test thoroughly before committing

## 9. Subscription Types Reference

| Type | Use Case | Example File |
| ---- | -------- | ------------ |
| Accounts | Monitor specific account changes | `accounts_basic_filter.py` |
| Transactions | Track transaction activity | `transactions_basic_filter.py` |
| Slots | Monitor slot progression | `slots_subscription.py` |
| Blocks | Subscribe to full blocks | `blocks_subscription.py` |
| Block Metadata | Lightweight block tracking | `blocks_meta_subscription.py` |
| Entries | Low-level ledger changes | `entries_subscription.py` |
| Transaction Status | Track tx finalization | `transaction_statuses_subscription.py` |

## 10. Useful Commands Recap

| Command                                    | Purpose                          |
| ------------------------------------------ | -------------------------------- |
| `uv sync`                                  | Install/update dependencies      |
| `uv run main.py`                           | Run the main monitor             |
| `uv run learning-examples/<example>.py`    | Run specific example             |
| `uv run ruff format`                       | Format code                      |
| `uv run ruff check`                        | Lint code                        |

## 11. Safety Reminders

* **Never expose API tokens** in code or commits.
* **Test filters carefully** to avoid overwhelming the gRPC endpoint.
* **Monitor rate limits** and connection stability.
* **Handle disconnections gracefully** with retry logic.
* **Log errors** for debugging connection issues.

---

Following these practices ensures reliable Geyser development, prevents connection issues, and maintains code quality. Always test filters progressively from simple to complex when developing new monitoring capabilities.