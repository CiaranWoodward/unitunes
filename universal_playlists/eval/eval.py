import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
import typer
from rich.console import Console
from universal_playlists.main import service_factory
from universal_playlists.services.services import StreamingService

from universal_playlists.types import ServiceType
from universal_playlists.uri import TrackURI, URI_from_url, trackURI_from_url


class Case(BaseModel):
    description: str = ""
    matches: List[str] = []
    non_matches: List[str] = []


eval_app = typer.Typer()
console = Console()

path = Path(__file__).absolute().parent / "data" / "cases.json"


def load_cases() -> List[Case]:
    with open(path) as f:
        raw = json.load(f)
    return [Case.parse_obj(case) for case in raw]


def save_cases(cases: List[Case]) -> None:
    with open(path, "w") as f:
        json.dump([case.dict() for case in cases], f, indent=4)


@eval_app.command()
def add(description: str, uri: str) -> None:
    """Add a new case"""
    cases = load_cases()
    cases.append(Case(description=description, matches=[uri]))
    save_cases(cases)


def build_service(service_type: ServiceType) -> StreamingService:
    path = (
        Path(__file__).parent
        / "data"
        / "service_configs"
        / f"{service_type}_config.json"
    )
    cache_path = Path(__file__).absolute().parent / "data" / "cache"
    service = service_factory(
        service_type, service_type, cache_path=cache_path, config_path=path
    )
    return service


@eval_app.command()
def search(
    guess_service: Optional[ServiceType] = typer.Option(None, "--guess", "-g")
) -> None:
    """
    Evaluate search performance.
    """
    cases = load_cases()

    for case in cases:
        console.print(f"Case: {case.description}", style="bold")
        matches = [trackURI_from_url(url) for url in case.matches]
        non_matches = [trackURI_from_url(url) for url in case.non_matches]
        matched_services = [uri.service for uri in matches]
        if guess_service is not None:
            matched_services.append(guess_service)

        for source_uri in matches:
            for target_type in matched_services:
                target_service = build_service(target_type)
                source_service = build_service(source_uri.service)
                source_track = source_service.pull_track(source_uri)
                guesses = target_service.search_track(source_track)[:3]
                best_guess = target_service.best_match(source_track)

                if best_guess and best_guess.uris[0] in matches:
                    console.print(
                        f"{source_uri.service} -> {target_type}",
                        style="green",
                    )
                    continue
                console.print(
                    f"{source_uri.service} -> {target_type}",
                    style="red",
                )

                console.print("Original:", end="\n\n")
                console.print(source_track, end="\n\n")
                console.print("Guesses:")

                for g in guesses:
                    uris_on_service = [
                        uri for uri in g.uris if uri.service == target_type
                    ]
                    assert len(uris_on_service) == 1
                    guess_uri = uris_on_service[0]

                    if guess_uri in matches:
                        console.print(g, style="green")
                    elif guess_uri in non_matches:
                        console.print(g, style="red")
                    else:
                        # ask user if this is the correct match
                        console.print(g)
                        correct = typer.confirm(f"Is {g.name.value} a correct match?")

                        if correct:
                            case.matches.append(guess_uri.url)
                            print("Added to matches")
                        else:
                            case.non_matches.append(guess_uri.url)
                            print("Added to non-matches")

                        save_cases(cases)
