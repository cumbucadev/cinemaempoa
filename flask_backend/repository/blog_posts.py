from datetime import datetime
from math import ceil
from typing import List, Optional, Tuple

from slugify import slugify
from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import BlogPost


def create(
    title: str,
    content: str,
    author_id: int,
    slug: Optional[str] = None,
    excerpt: Optional[str] = None,
    published: bool = False,
    featured_image: Optional[str] = None,
    featured_image_alt: Optional[str] = None,
) -> BlogPost:
    if slug is None:
        slug = slugify(title)

    # Ensure slug is unique
    original_slug = slug
    counter = 1
    while db_session.query(BlogPost).filter(BlogPost.slug == slug).first():
        slug = f"{original_slug}-{counter}"
        counter += 1

    blog_post = BlogPost(
        title=title,
        slug=slug,
        content=content,
        excerpt=excerpt,
        author_id=author_id,
        created_at=datetime.utcnow(),
        published=published,
        featured_image=featured_image,
        featured_image_alt=featured_image_alt,
    )

    db_session.add(blog_post)
    db_session.commit()
    db_session.refresh(blog_post)
    return blog_post


def get_all(include_unpublished: bool = False) -> List[BlogPost]:
    query = db_session.query(BlogPost)
    if not include_unpublished:
        query = query.filter(BlogPost.published == True)  # noqa: E712
    query = query.order_by(BlogPost.created_at.desc())
    return query.all()


def get_all_paginated(
    current_page: int, per_page: int, include_unpublished: bool = False
) -> Tuple[List[BlogPost], int, int]:
    offset_value = (current_page - 1) * per_page

    query = db_session.query(BlogPost)
    if not include_unpublished:
        query = query.filter(BlogPost.published == True)  # noqa: E712

    query = (
        query.order_by(BlogPost.created_at.desc()).limit(per_page).offset(offset_value)
    )
    posts = query.all()

    count_query = db_session.query(func.count(BlogPost.id))
    if not include_unpublished:
        count_query = count_query.filter(BlogPost.published == True)  # noqa: E712

    total_count = count_query.scalar()
    total_pages = ceil(total_count / per_page)

    return (posts, total_pages, total_count)


def get_by_id(post_id: int) -> Optional[BlogPost]:
    return db_session.query(BlogPost).filter(BlogPost.id == post_id).first()


def get_by_slug(slug: str) -> Optional[BlogPost]:
    return db_session.query(BlogPost).filter(BlogPost.slug == slug).first()


def update(
    post_id: int,
    title: Optional[str] = None,
    content: Optional[str] = None,
    slug: Optional[str] = None,
    excerpt: Optional[str] = None,
    published: Optional[bool] = None,
    featured_image: Optional[str] = None,
    featured_image_alt: Optional[str] = None,
) -> Optional[BlogPost]:
    post = get_by_id(post_id)
    if not post:
        return None

    if title is not None:
        post.title = title
        # Update slug if title changed and no specific slug provided
        if slug is None:
            slug = slugify(title)

    if slug is not None:
        # Ensure slug is unique (excluding current post)
        original_slug = slug
        counter = 1
        while (
            db_session.query(BlogPost)
            .filter(BlogPost.slug == slug, BlogPost.id != post_id)
            .first()
        ):
            slug = f"{original_slug}-{counter}"
            counter += 1
        post.slug = slug

    if content is not None:
        post.content = content

    if excerpt is not None:
        post.excerpt = excerpt

    if published is not None:
        post.published = published

    if featured_image is not None:
        post.featured_image = featured_image

    if featured_image_alt is not None:
        post.featured_image_alt = featured_image_alt

    post.updated_at = datetime.utcnow()

    db_session.commit()
    db_session.refresh(post)
    return post


def delete(post_id: int) -> bool:
    post = get_by_id(post_id)
    if not post:
        return False

    db_session.delete(post)
    db_session.commit()
    return True


def toggle_published(post_id: int) -> Optional[BlogPost]:
    post = get_by_id(post_id)
    if not post:
        return None

    post.published = not post.published
    post.updated_at = datetime.utcnow()

    db_session.commit()
    db_session.refresh(post)
    return post
