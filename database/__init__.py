# project_QLE/database/__init__.py
from .db   import (init_database, get_session, create_project, get_project,
                   list_projects, delete_project, save_well, get_wells_in_project,
                   save_petro_data_batch, save_formation_top, save_dst_test,
                   save_interpretation, save_ml_model, get_ml_models_for_project)
from .auth import (init_auth, authenticate, is_owner, create_user,
                   deactivate_user, reactivate_user, regenerate_key,
                   list_users, delete_user)

def init_all():
    """Initialise both database tables and auth tables."""
    init_database()
    init_auth()

__all__ = [
    "init_all", "init_database", "init_auth", "get_session",
    "create_project", "get_project", "list_projects", "delete_project",
    "save_well", "get_wells_in_project",
    "save_petro_data_batch", "save_formation_top", "save_dst_test",
    "save_interpretation", "save_ml_model", "get_ml_models_for_project",
    "authenticate", "is_owner", "create_user", "deactivate_user",
    "reactivate_user", "regenerate_key", "list_users", "delete_user",
]