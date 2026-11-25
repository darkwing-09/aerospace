import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from connectors.base import BaseConnector, ConnectionResult, RawResource

class LocalWikiConnector(BaseConnector):
    """
    First enterprise connector: Local Filesystem / Enterprise Markdown Wiki connector.
    Reads structured documentation repositories, extracts ACL and classification frontmatter,
    and enforces approval gates on modifications.
    """
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)

    def connect(self) -> ConnectionResult:
        if not self.root_dir.exists():
            return ConnectionResult(success=False, message=f"Root directory not found: {self.root_dir}", status_code=404)
        return ConnectionResult(success=True, message="Connected to local wiki repository", status_code=200)

    def discover_resources(self) -> List[str]:
        if not self.root_dir.exists():
            return []
        files = []
        for p in self.root_dir.glob("**/*"):
            if p.is_file() and p.suffix.lower() in [".md", ".txt", ".wiki"]:
                rel_path = str(p.relative_to(self.root_dir))
                files.append(rel_path)
        return sorted(files)

    def fetch_resource(self, resource_id: str) -> RawResource:
        file_path = self.root_dir / resource_id
        if not file_path.exists():
            raise FileNotFoundError(f"Resource not found: {file_path}")

        raw_text = file_path.read_text(encoding="utf-8")
        
        # Parse simple YAML-like frontmatter if present
        title = file_path.stem
        classification = "INTERNAL"
        acls: List[str] = []
        content = raw_text

        if raw_text.startswith("---"):
            parts = raw_text.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                content = parts[2].strip()
                
                # Extract title
                m_title = re.search(r"title:\s*(.+)", frontmatter)
                if m_title:
                    title = m_title.group(1).strip()
                    
                # Extract classification
                m_class = re.search(r"classification:\s*(.+)", frontmatter)
                if m_class:
                    classification = m_class.group(1).strip()
                    
                # Extract ACLs
                m_acls = re.findall(r"-\s*([a-zA-Z0-9_:]+)", frontmatter)
                if m_acls:
                    acls = [a.strip() for a in m_acls]

        return RawResource(
            resource_id=resource_id,
            source_uri=f"file://{file_path.resolve()}",
            title=title,
            content=content,
            content_type="wiki_document",
            acls=acls,
            classification_level=classification,
            metadata={"file_name": file_path.name, "size_bytes": file_path.stat().st_size},
            timestamp=datetime.now(timezone.utc)
        )

    def _execute_write_action(self, resource_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        file_path = self.root_dir / resource_id
        if action == "update_content":
            append_text = payload.get("append_text", "")
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(append_text)
            return {
                "status": "EXECUTED",
                "success": True,
                "action": action,
                "resource_id": resource_id,
                "bytes_written": len(append_text)
            }
        elif action == "create_document":
            new_content = payload.get("content", "")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return {
                "status": "EXECUTED",
                "success": True,
                "action": action,
                "resource_id": resource_id
            }
        else:
            raise ValueError(f"Unsupported write action: '{action}'")

