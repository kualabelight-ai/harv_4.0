# database_settings/models.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import warnings
warnings.filterwarnings("ignore", message=r".*ScriptRunContext.*")

class PermissionLevel(Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    FULL_ACCESS = "full_access"


@dataclass
class APIKey:
    id: int
    site_name: str
    domain_name: Optional[str]
    provider: str
    api_key: str
    is_active: bool
    created_by: int
    created_at: datetime
    last_used_at: Optional[datetime]
    notes: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'site_name': self.site_name,
            'domain_name': self.domain_name,
            'provider': self.provider,
            'api_key': self.api_key,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'notes': self.notes
        }


@dataclass
class APIUsageLog:
    id: int
    user_id: int
    project_id: Optional[str]
    site_name: str
    domain_name: str
    provider: str
    model: str
    request_type: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Optional[float]
    request_duration_ms: Optional[int]
    success: bool
    error_message: Optional[str]
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'project_id': self.project_id,
            'site_name': self.site_name,
            'domain_name': self.domain_name,
            'provider': self.provider,
            'model': self.model,
            'request_type': self.request_type,
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'total_tokens': self.total_tokens,
            'estimated_cost': self.estimated_cost,
            'request_duration_ms': self.request_duration_ms,
            'success': self.success,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class UserDomainPermission:
    id: int
    user_id: int
    site_name: str
    domain_name: str
    can_read: bool
    can_write: bool
    can_delete: bool
    granted_by: int
    granted_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'site_name': self.site_name,
            'domain_name': self.domain_name,
            'can_read': self.can_read,
            'can_write': self.can_write,
            'can_delete': self.can_delete,
            'granted_by': self.granted_by,
            'granted_at': self.granted_at.isoformat() if self.granted_at else None
        }


@dataclass
class AdminAuditLog:
    id: int
    admin_id: int
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    details: Optional[str]
    ip_address: Optional[str]
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'admin_id': self.admin_id,
            'action': self.action,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'details': self.details,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }