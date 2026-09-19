"""GitHub GraphQL helpers for creating Projects V2 and draft items."""

from __future__ import annotations

from typing import Any

import requests

from .config import AppConfig


GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"


class GitHubAPIError(RuntimeError):
    """Raised when a GitHub GraphQL request fails."""


def _graphql_request(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }

    try:
        response = requests.post(
            GITHUB_GRAPHQL_URL,
            headers=headers,
            json={"query": query, "variables": variables},
            timeout=60,
        )
    except requests.RequestException as exc:
        raise GitHubAPIError(f"GitHub request failed: {exc}") from exc

    if response.status_code >= 400:
        raise GitHubAPIError(
            f"GitHub API error {response.status_code}: {response.text.strip() or 'no response body'}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise GitHubAPIError("GitHub returned a non-JSON HTTP response.") from exc

    errors = payload.get("errors")
    if errors:
        messages = "; ".join(error.get("message", "Unknown GitHub GraphQL error") for error in errors)
        raise GitHubAPIError(messages)

    data = payload.get("data")
    if not isinstance(data, dict):
        raise GitHubAPIError("GitHub response was missing a top-level data object.")

    return data


def _resolve_owner(token: str, owner_login: str) -> dict[str, str]:
    query = """
    query ResolveOwner($login: String!) {
      user(login: $login) {
        id
        login
      }
      organization(login: $login) {
        id
        login
      }
    }
    """

    data = _graphql_request(token, query, {"login": owner_login})

    if data.get("user"):
        return {
            "id": data["user"]["id"],
            "login": data["user"]["login"],
            "type": "User",
        }

    if data.get("organization"):
        return {
            "id": data["organization"]["id"],
            "login": data["organization"]["login"],
            "type": "Organization",
        }

    raise GitHubAPIError(
        f"Could not resolve GITHUB_OWNER '{owner_login}' as a GitHub user or organization."
    )


def _format_draft_item(project_description: str, item: dict[str, Any]) -> tuple[str, str]:
    title = f"[{item['type']}] {item['title']}"
    body = (
        f"Project Description: {project_description}\n\n"
        f"Type: {item['type']}\n"
        f"Priority: {item['priority']}\n"
        f"Confidence: {item['confidence']}\n"
        f"Phase: {item['phase']}\n"
        f"Needs Review: {'Yes' if item['needs_review'] else 'No'}\n\n"
        f"{item['body']}"
    )
    return title, body


def create_project_with_draft_items(
    project_data: dict[str, Any], config: AppConfig
) -> dict[str, Any]:
    """Create a GitHub Project V2 and add one draft item for each extracted item."""

    owner = _resolve_owner(config.github_token, config.github_owner)

    # GitHub's current CreateProjectV2Input supports title on creation, but not
    # shortDescription/readme, so V1 creates the project with title only.
    create_project_mutation = """
    mutation CreateProject($ownerId: ID!, $title: String!) {
      createProjectV2(input: {ownerId: $ownerId, title: $title}) {
        projectV2 {
          id
          title
          url
        }
      }
    }
    """

    create_result = _graphql_request(
        config.github_token,
        create_project_mutation,
        {
            "ownerId": owner["id"],
            "title": project_data["project_title"],
        },
    )

    project = (
        create_result.get("createProjectV2", {}).get("projectV2")
        if isinstance(create_result.get("createProjectV2"), dict)
        else None
    )
    if not isinstance(project, dict):
        raise GitHubAPIError("GitHub did not return the created project data.")

    add_draft_mutation = """
    mutation AddDraftIssue($projectId: ID!, $title: String!, $body: String!) {
      addProjectV2DraftIssue(input: {projectId: $projectId, title: $title, body: $body}) {
        projectItem {
          id
        }
      }
    }
    """

    added_item_ids: list[str] = []
    for index, item in enumerate(project_data["items"], start=1):
        draft_title, draft_body = _format_draft_item(project_data["project_description"], item)
        try:
            add_result = _graphql_request(
                config.github_token,
                add_draft_mutation,
                {
                    "projectId": project["id"],
                    "title": draft_title,
                    "body": draft_body,
                },
            )
        except GitHubAPIError as exc:
            raise GitHubAPIError(
                f"Failed to add draft item {index} ('{item['title']}'): {exc}"
            ) from exc

        project_item = (
            add_result.get("addProjectV2DraftIssue", {}).get("projectItem")
            if isinstance(add_result.get("addProjectV2DraftIssue"), dict)
            else None
        )
        if not isinstance(project_item, dict) or not isinstance(project_item.get("id"), str):
            raise GitHubAPIError(
                f"GitHub did not return an item id for draft item {index} ('{item['title']}')."
            )

        added_item_ids.append(project_item["id"])

    return {
        "project_id": project["id"],
        "project_url": project.get("url"),
        "project_title": project.get("title", project_data["project_title"]),
        "owner_login": owner["login"],
        "owner_type": owner["type"],
        "items_added": len(added_item_ids),
        "draft_item_ids": added_item_ids,
    }
