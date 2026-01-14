# Database Migrations with Alembic

This project uses Alembic for database schema migrations.

## Prerequisites

Make sure you have:
- Virtual environment activated: `source venv/bin/activate`
- DATABASE_URL set in your `.env` file

## Common Commands

### Check current migration version
```bash
alembic current
```

### View migration history
```bash
alembic history
```

### Create a new migration
```bash
alembic revision -m "description_of_changes"
```

### Apply all pending migrations
```bash
alembic upgrade head
```

### Rollback one migration
```bash
alembic downgrade -1
```

### Rollback to specific version
```bash
alembic downgrade <revision_id>
```

## Migration File Structure

Migration files are located in `alembic/versions/`. Each file contains:
- `upgrade()` - SQL to apply the migration
- `downgrade()` - SQL to rollback the migration

Since we're using asyncpg (not SQLAlchemy ORM), migrations use raw SQL via `op.execute()`.

## Example Migration

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE example (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL
        )
    """)

def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS example")
```

## Environment Configuration

The migration environment (`alembic/env.py`) is configured for:
- **Async support** with asyncpg
- **Environment variables** - Reads DATABASE_URL from .env
- **Raw SQL** - No SQLAlchemy ORM models (target_metadata = None)

## Best Practices

1. Always test migrations locally before deploying
2. Never edit existing migration files - create new ones
3. Keep migrations small and focused
4. Add both upgrade and downgrade paths
5. Use descriptive migration names
6. Test rollback functionality

## Troubleshooting

### "greenlet library is required"
```bash
pip install greenlet
```

### "DATABASE_URL not set"
Make sure `.env` file exists with:
```
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

### Migration conflicts
If you have multiple branches with migrations, ensure they merge properly:
```bash
alembic history
# Check for branches in the revision tree
```
