"""Enterprise document retrieval for NOVA (Part 6).

This package intentionally avoids eager re-exports. The agent and router
packages import each other indirectly, so lazy module imports keep FastAPI
startup free of circular-import side effects.
"""
