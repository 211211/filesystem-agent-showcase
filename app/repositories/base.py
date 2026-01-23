"""Base repository interface for data access layer.

This module provides a generic repository pattern interface that can be
implemented for different data sources (database, file system, cache, etc.).
"""

from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar

# Generic type variable for entity types
T = TypeVar("T")


class Repository(ABC, Generic[T]):
    """Abstract base class for repository pattern implementation.

    This generic repository provides a standard interface for data access
    operations across different storage backends. Implement this interface
    for specific entity types and storage mechanisms.

    Type Parameters:
        T: The type of entity this repository manages

    Example:
        ```python
        class UserRepository(Repository[User]):
            def get(self, id: str) -> Optional[User]:
                # Implementation for fetching user by ID
                pass

            def get_all(self) -> List[User]:
                # Implementation for fetching all users
                pass
        ```
    """

    @abstractmethod
    def get(self, id: str) -> Optional[T]:
        """Retrieve a single entity by its identifier.

        Args:
            id: The unique identifier of the entity

        Returns:
            The entity if found, None otherwise

        Raises:
            NotImplementedError: This is an abstract method
        """
        pass

    @abstractmethod
    def get_all(self) -> List[T]:
        """Retrieve all entities from the repository.

        Returns:
            A list of all entities. Returns empty list if none exist.

        Raises:
            NotImplementedError: This is an abstract method
        """
        pass

    @abstractmethod
    def add(self, entity: T) -> T:
        """Add a new entity to the repository.

        Args:
            entity: The entity to add

        Returns:
            The added entity (may include generated ID or timestamps)

        Raises:
            NotImplementedError: This is an abstract method
        """
        pass

    @abstractmethod
    def update(self, id: str, entity: T) -> Optional[T]:
        """Update an existing entity in the repository.

        Args:
            id: The unique identifier of the entity to update
            entity: The updated entity data

        Returns:
            The updated entity if found and updated, None otherwise

        Raises:
            NotImplementedError: This is an abstract method
        """
        pass

    @abstractmethod
    def delete(self, id: str) -> bool:
        """Delete an entity from the repository.

        Args:
            id: The unique identifier of the entity to delete

        Returns:
            True if the entity was deleted, False if not found

        Raises:
            NotImplementedError: This is an abstract method
        """
        pass

    @abstractmethod
    def exists(self, id: str) -> bool:
        """Check if an entity exists in the repository.

        Args:
            id: The unique identifier to check

        Returns:
            True if the entity exists, False otherwise

        Raises:
            NotImplementedError: This is an abstract method
        """
        pass
