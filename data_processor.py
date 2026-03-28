import pandas as pd
import numpy as np
import config
from typing import Dict, List, Optional, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataValidator:
    """Validates and sanitizes data from Quire API"""
    
    @staticmethod
    def validate_row(row: pd.Series) -> Tuple[bool, List[str]]:
        """Validate a single row of data"""
        errors = []
        
        # Check required fields
        if pd.isna(row.get('name')) or str(row.get('name')).strip() == '':
            errors.append("Missing task name")
        
        if pd.isna(row.get('project_id')) or str(row.get('project_id')).strip() == '':
            errors.append("Missing project_id")
        
        # Validate status_value range
        status = row.get('status_value', 0)
        if not isinstance(status, (int, float)) or status < 0 or status > 100:
            errors.append(f"Invalid status_value: {status}")
        
        # Validate time values
        for col in ['hours_week', 'hours_month', 'hours_total']:
            val = row.get(col, 0)
            if not isinstance(val, (int, float)) or val < 0:
                errors.append(f"Invalid {col}: {val}")
            elif val > 168:  # More than 168 hours in a week is suspicious
                logger.warning(f"Suspicious {col} value: {val} for task {row.get('name')}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Validate entire dataframe and log issues"""
        if df.empty:
            logger.warning("Empty dataframe received")
            return df
        
        invalid_rows = []
        for idx, row in df.iterrows():
            is_valid, errors = DataValidator.validate_row(row)
            if not is_valid:
                logger.error(f"Row {idx} validation failed: {errors}")
                invalid_rows.append(idx)
        
        if invalid_rows:
            logger.warning(f"Removing {len(invalid_rows)} invalid rows")
            df = df.drop(invalid_rows)
        
        return df


class AssigneeProcessor:
    """Optimized assignee processing with caching"""
    
    def __init__(self):
        # Pre-compute lowercase mappings for faster lookups
        self.assignee_names_lower = {name.lower(): name for name in config.ASSIGNEE_NAMES}
        self.name_norm_lower = {k.lower(): v for k, v in config.NAME_NORMALIZATION.items()}
        self.rule_mapping_lower = {k.lower(): v for k, v in config.RULE_MAPPING.items()}
        self._cache = {}
    
    def process_assignee(self, assignee: str, tags_str: str) -> str:
        """
        Process assignee with prioritized logic:
        LEVEL 0: Override ONLY for 'Rey' found in tags.
        LEVEL 1: Direct assignment from Quire.
        LEVEL 2: Extract from tags (other people).
        LEVEL 3: Fallback mapping by profession rules.
        """
        # Check cache
        cache_key = f"{assignee}|{tags_str}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        result = self._process_assignee_internal(assignee, tags_str)
        self._cache[cache_key] = result
        return result
    
    def _process_assignee_internal(self, assignee: str, tags_str: str) -> str:
        # Pre-process tags
        tags_list = [t.strip() for t in str(tags_str).split(',') if t.strip()]
        
        # Buscar si hay algún nombre válido en los tags
        found_name_in_tags = self._find_name_in_tags(tags_list)
        
        # LEVEL 0: SPECIAL OVERRIDE FOR REY
        # Si encontramos a "Rey" en los tags, lo asignamos inmediatamente,
        # ignorando a quien esté asignado en Quire.
        if found_name_in_tags == "Rey":
            return "Rey"

        # LEVEL 1: Direct assignment from Quire
        # Si Quire tiene un asignado (y no es Unassigned), usamos ese.
        if assignee and assignee.strip() and assignee != "Unassigned":
            return self._normalize_names(assignee)
        
        # LEVEL 2: Search in tags (Fallback for others)
        # Si no había asignado en Quire, pero encontramos un nombre en los tags (ej. Hugo), lo usamos.
        if found_name_in_tags:
            return self._normalize_names(found_name_in_tags)
        
        # LEVEL 3: Rule mapping fallback (Por profesión/tipo de trabajo)
        return self._apply_rule_mapping(tags_str, "Unassigned")
    
    def _find_name_in_tags(self, tags_list: List[str]) -> Optional[str]:
        """Find assignee name in tags list - Fixed KeyError logic"""
        for tag in tags_list:
            tag_lower = tag.lower()
            
            # 1. Check normalization mapping (e.g. "Ray" -> "Rey", "Averdezza" -> "Manuel")
            # Corrección del Error: Accedemos directamente al valor mapeado en self.name_norm_lower
            if tag_lower in self.name_norm_lower:
                normalized_name = self.name_norm_lower[tag_lower]
                return normalized_name
            
            # 2. Check strict containment (e.g., tag "Rey" inside list)
            if tag_lower in self.assignee_names_lower:
                return self.assignee_names_lower[tag_lower]
                
        return None
    
    def _apply_rule_mapping(self, tags_str: str, default: str) -> str:
        """Apply profession-based mapping"""
        if not tags_str:
            return default
            
        tags_lower = tags_str.lower()
        for tag_key_lower, person in self.rule_mapping_lower.items():
            if tag_key_lower in tags_lower:
                return person
        return default
    
    def _normalize_names(self, assignee: str) -> str:
        """Normalize and deduplicate names"""
        if not assignee or assignee == "Unassigned":
            return assignee
        
        names = assignee.split(',')
        normalized_names = []
        
        for n in names:
            n = n.strip()
            # Use lowercase lookup for case-insensitive matching
            norm = config.NAME_NORMALIZATION.get(n, n)
            normalized_names.append(norm)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_names = []
        for name in normalized_names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)
        
        return ",".join(unique_names)


def process_tags_vectorized(tags_series: pd.Series) -> pd.Series:
    """Vectorized tag processing"""
    allowed_tags_set = set(config.ALLOWED_TAGS)
    
    def find_tag(tags_str):
        if not tags_str:
            return "Other"
        current_tags = tags_str.split(',')
        for tag in current_tags:
            clean_tag = tag.strip()
            if clean_tag in allowed_tags_set:
                return clean_tag
        return "Other"
    
    return tags_series.apply(find_tag)


def get_processed_dataframe(raw_data: List[Dict]) -> pd.DataFrame:
    """
    Main processing function with validation and optimization
    """
    logger.info(f"Processing {len(raw_data)} raw records")
    
    # Create dataframe
    df = pd.DataFrame(raw_data)
    
    if df.empty:
        logger.warning("Empty dataframe")
        return df
    
    # Validate data
    df = DataValidator.validate_dataframe(df)
    
    # Filter exclusions (vectorized)
    exclusion_set = set(config.EXCLUSION_LIST)
    df = df[~df['name'].isin(exclusion_set)]
    logger.info(f"After exclusions: {len(df)} records")
    
    # Process assignees
    processor = AssigneeProcessor()
    
    # Usar .get() para evitar errores si las columnas no existen
    df['Assignee'] = df.apply(
        lambda row: processor.process_assignee(
            row.get('raw_assignees', ''), 
            row.get('raw_tags', '')
        ), 
        axis=1
    )
    
    # Process tags (vectorized)
    df['Tag'] = process_tags_vectorized(df['raw_tags'])
    
    # Parse timestamps
    df['completed_at_parsed'] = pd.to_datetime(df['completed_at'], errors='coerce')
    
    # Compute completion status
    df['is_completed'] = df['status_value'] >= 100
    
    # Ensure numeric columns (vectorized)
    numeric_cols = ['hours_week', 'hours_month', 'hours_total']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Additional validation: Cap extreme values
    for col in numeric_cols:
        max_reasonable = 168 if 'week' in col else 720  # 168h/week, 720h/month
        df.loc[df[col] > max_reasonable, col] = max_reasonable
    
    logger.info(f"Successfully processed {len(df)} records")
    logger.info(f"Assignee distribution:\n{df['Assignee'].value_counts()}")
    
    return df


def get_data_quality_report(df: pd.DataFrame) -> Dict:
    """Generate data quality metrics"""
    if df.empty:
        return {"status": "empty", "message": "No data to analyze"}
    
    report = {
        "total_records": len(df),
        "missing_assignees": (df['Assignee'] == 'Unassigned').sum(),
        "missing_time_logs": {
            "week": (df['hours_week'] == 0).sum(),
            "month": (df['hours_month'] == 0).sum(),
            "total": (df['hours_total'] == 0).sum()
        },
        "completed_without_time": len(df[(df['is_completed']) & (df['hours_total'] == 0)]),
        "tag_distribution": df['Tag'].value_counts().to_dict(),
        "projects_count": df['project_id'].nunique(),
        "date_range": {
            "earliest": df['completed_at_parsed'].min(),
            "latest": df['completed_at_parsed'].max()
        } if df['completed_at_parsed'].notna().any() else None
    }
    
    return report
