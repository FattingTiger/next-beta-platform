from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from beta_center.models import (
    App,
    AppStatus,
    Bug,
    BugVisibility,
    TestGroup,
    User,
    UserRole,
    app_group_visibility,
    user_group_members,
)


def user_can_access_app(db: Session, user: User, app_id: str) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if not user.is_active:
        return False
    query = select(
        exists()
        .where(App.id == app_id, App.status == AppStatus.PUBLISHED)
        .where(app_group_visibility.c.app_id == App.id)
        .where(app_group_visibility.c.group_id == TestGroup.id, TestGroup.is_active.is_(True))
        .where(user_group_members.c.group_id == TestGroup.id, user_group_members.c.user_id == user.id)
    )
    return bool(db.scalar(query))


def accessible_app_ids_query(user: User):  # type: ignore[no-untyped-def]
    if user.role == UserRole.ADMIN:
        return select(App.id)
    return (
        select(App.id)
        .join(app_group_visibility, app_group_visibility.c.app_id == App.id)
        .join(TestGroup, TestGroup.id == app_group_visibility.c.group_id)
        .join(user_group_members, user_group_members.c.group_id == TestGroup.id)
        .where(
            user_group_members.c.user_id == user.id,
            TestGroup.is_active.is_(True),
            App.status == AppStatus.PUBLISHED,
        )
    )


def user_can_view_bug(db: Session, user: User, bug: Bug) -> bool:
    if bug.deleted_at is not None:
        return False
    if user.role == UserRole.ADMIN or bug.reporter_id == user.id:
        return True
    if bug.visibility == BugVisibility.PRIVATE:
        return False
    return user_can_access_app(db, user, bug.app_id)


def user_can_view_bug_attachment(db: Session, user: User, bug: Bug) -> bool:
    # Screenshots can contain notifications, names, account data, or other
    # device content.  Group visibility applies to the written issue summary,
    # never to raw evidence files.
    if bug.deleted_at is not None:
        return False
    _ = db
    return user.role == UserRole.ADMIN or bug.reporter_id == user.id
