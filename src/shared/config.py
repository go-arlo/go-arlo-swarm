from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional

def configure_cors(app: FastAPI, additional_origins: Optional[List[str]] = None):
    """
    Configure CORS middleware for FastAPI applications.
    
    Args:
        app: The FastAPI application instance
        additional_origins: Optional list of additional origins to allow
    """

    default_origins = [
        "http://localhost:3000",
        "https://go-arlo-ui-production.up.railway.app"
    ]
    
    default_origins = [origin for origin in default_origins if origin]
    
    # Combine default origins with any additional origins
    all_origins = default_origins.copy()
    if additional_origins:
        all_origins.extend(additional_origins)
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=all_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    return app
