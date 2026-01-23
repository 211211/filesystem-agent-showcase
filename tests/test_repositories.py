"""Unit tests for repository base interface.

Tests the abstract Repository base class and validates the repository pattern
implementation requirements.
"""

from typing import List, Optional

import pytest

from app.repositories.base import Repository


# Test entity class
class User:
    """Mock entity for testing repository interface."""

    def __init__(self, id: str, name: str, email: str):
        self.id = id
        self.name = name
        self.email = email

    def __eq__(self, other):
        if not isinstance(other, User):
            return False
        return self.id == other.id and self.name == other.name and self.email == other.email


# Mock repository implementation for testing
class InMemoryUserRepository(Repository[User]):
    """In-memory implementation of Repository for testing purposes."""

    def __init__(self):
        self._storage: dict[str, User] = {}

    def get(self, id: str) -> Optional[User]:
        return self._storage.get(id)

    def get_all(self) -> List[User]:
        return list(self._storage.values())

    def add(self, entity: User) -> User:
        self._storage[entity.id] = entity
        return entity

    def update(self, id: str, entity: User) -> Optional[User]:
        if id not in self._storage:
            return None
        self._storage[id] = entity
        return entity

    def delete(self, id: str) -> bool:
        if id not in self._storage:
            return False
        del self._storage[id]
        return True

    def exists(self, id: str) -> bool:
        return id in self._storage


class TestRepositoryAbstraction:
    """Tests for Repository abstract base class."""

    def test_cannot_instantiate_abstract_repository(self):
        """Test that Repository cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            Repository()  # type: ignore

    def test_must_implement_all_abstract_methods(self):
        """Test that all abstract methods must be implemented."""

        class IncompleteRepository(Repository[User]):
            """Incomplete repository missing required methods."""

            pass

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteRepository()  # type: ignore

    def test_concrete_implementation_can_be_instantiated(self):
        """Test that a complete implementation can be instantiated."""
        repo = InMemoryUserRepository()
        assert isinstance(repo, Repository)


class TestInMemoryUserRepository:
    """Tests for the mock InMemoryUserRepository implementation."""

    @pytest.fixture
    def repository(self):
        """Provide a fresh repository instance for each test."""
        return InMemoryUserRepository()

    @pytest.fixture
    def sample_user(self):
        """Provide a sample user entity."""
        return User(id="1", name="Alice", email="alice@example.com")

    def test_add_and_get(self, repository: InMemoryUserRepository, sample_user: User):
        """Test adding and retrieving an entity."""
        added = repository.add(sample_user)
        assert added == sample_user

        retrieved = repository.get(sample_user.id)
        assert retrieved is not None
        assert retrieved.id == sample_user.id
        assert retrieved.name == sample_user.name
        assert retrieved.email == sample_user.email

    def test_get_nonexistent_returns_none(self, repository: InMemoryUserRepository):
        """Test that getting a nonexistent entity returns None."""
        result = repository.get("nonexistent")
        assert result is None

    def test_get_all_empty(self, repository: InMemoryUserRepository):
        """Test that get_all returns empty list when repository is empty."""
        result = repository.get_all()
        assert result == []

    def test_get_all_multiple_entities(self, repository: InMemoryUserRepository):
        """Test retrieving multiple entities."""
        user1 = User(id="1", name="Alice", email="alice@example.com")
        user2 = User(id="2", name="Bob", email="bob@example.com")
        user3 = User(id="3", name="Charlie", email="charlie@example.com")

        repository.add(user1)
        repository.add(user2)
        repository.add(user3)

        all_users = repository.get_all()
        assert len(all_users) == 3
        assert user1 in all_users
        assert user2 in all_users
        assert user3 in all_users

    def test_update_existing_entity(self, repository: InMemoryUserRepository, sample_user: User):
        """Test updating an existing entity."""
        repository.add(sample_user)

        updated_user = User(id="1", name="Alice Updated", email="alice.new@example.com")
        result = repository.update(sample_user.id, updated_user)

        assert result is not None
        assert result.name == "Alice Updated"
        assert result.email == "alice.new@example.com"

        # Verify the update persisted
        retrieved = repository.get(sample_user.id)
        assert retrieved is not None
        assert retrieved.name == "Alice Updated"

    def test_update_nonexistent_returns_none(self, repository: InMemoryUserRepository):
        """Test that updating a nonexistent entity returns None."""
        user = User(id="999", name="Nonexistent", email="none@example.com")
        result = repository.update("999", user)
        assert result is None

    def test_delete_existing_entity(self, repository: InMemoryUserRepository, sample_user: User):
        """Test deleting an existing entity."""
        repository.add(sample_user)
        assert repository.exists(sample_user.id)

        result = repository.delete(sample_user.id)
        assert result is True
        assert not repository.exists(sample_user.id)

    def test_delete_nonexistent_returns_false(self, repository: InMemoryUserRepository):
        """Test that deleting a nonexistent entity returns False."""
        result = repository.delete("nonexistent")
        assert result is False

    def test_exists_with_existing_entity(
        self, repository: InMemoryUserRepository, sample_user: User
    ):
        """Test exists returns True for existing entity."""
        repository.add(sample_user)
        assert repository.exists(sample_user.id) is True

    def test_exists_with_nonexistent_entity(self, repository: InMemoryUserRepository):
        """Test exists returns False for nonexistent entity."""
        assert repository.exists("nonexistent") is False


class TestRepositoryTypeHints:
    """Tests for proper type hint functionality."""

    def test_repository_generic_type_parameter(self):
        """Test that Repository accepts generic type parameter."""
        # This test validates that the type system accepts the generic parameter
        repo: Repository[User] = InMemoryUserRepository()
        assert isinstance(repo, Repository)

    def test_get_returns_optional_type(self):
        """Test that get() method returns Optional[T]."""
        repo = InMemoryUserRepository()
        user = User(id="1", name="Test", email="test@example.com")
        repo.add(user)

        # Type checker should recognize this as Optional[User]
        result: Optional[User] = repo.get("1")
        assert result is not None
        assert isinstance(result, User)

    def test_get_all_returns_list_type(self):
        """Test that get_all() method returns List[T]."""
        repo = InMemoryUserRepository()
        user = User(id="1", name="Test", email="test@example.com")
        repo.add(user)

        # Type checker should recognize this as List[User]
        result: List[User] = repo.get_all()
        assert isinstance(result, list)
        assert all(isinstance(u, User) for u in result)

    def test_add_accepts_and_returns_entity_type(self):
        """Test that add() accepts and returns the entity type."""
        repo = InMemoryUserRepository()
        user = User(id="1", name="Test", email="test@example.com")

        # Type checker should recognize parameter and return type
        result: User = repo.add(user)
        assert isinstance(result, User)
        assert result.id == user.id


class TestRepositoryEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def repository(self):
        """Provide a fresh repository instance for each test."""
        return InMemoryUserRepository()

    def test_add_duplicate_id_overwrites(self, repository: InMemoryUserRepository):
        """Test behavior when adding entity with duplicate ID."""
        user1 = User(id="1", name="Original", email="original@example.com")
        user2 = User(id="1", name="Duplicate", email="duplicate@example.com")

        repository.add(user1)
        repository.add(user2)

        retrieved = repository.get("1")
        assert retrieved is not None
        assert retrieved.name == "Duplicate"  # Last one wins

    def test_operations_on_empty_repository(self, repository: InMemoryUserRepository):
        """Test that operations on empty repository behave correctly."""
        assert repository.get("any") is None
        assert repository.get_all() == []
        assert repository.update("any", User("any", "Name", "email@example.com")) is None
        assert repository.delete("any") is False
        assert repository.exists("any") is False

    def test_multiple_operations_sequence(self, repository: InMemoryUserRepository):
        """Test a sequence of operations maintains consistency."""
        user = User(id="1", name="Alice", email="alice@example.com")

        # Add
        repository.add(user)
        assert repository.exists("1")

        # Update
        updated = User(id="1", name="Alice Updated", email="alice2@example.com")
        repository.update("1", updated)
        retrieved = repository.get("1")
        assert retrieved is not None
        assert retrieved.name == "Alice Updated"

        # Delete
        repository.delete("1")
        assert not repository.exists("1")
        assert repository.get("1") is None
