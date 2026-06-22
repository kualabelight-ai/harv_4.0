# ============================================
# 1. НОВЫЙ КЛАСС FileDataManager (добавить в новый файл file_data_manager.py)
# ============================================

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import streamlit as st
import shutil
from domain_manager import DomainManager


class FileDataManager:
    """
    ЕДИНСТВЕННЫЙ источник правды - РАБОТАЕТ НАПРЯМУЮ С ФАЙЛАМИ
    Никакой синхронизации, всё сразу пишется в файл
    """

    def __init__(self):
        pass

    def _get_current_domain(self) -> tuple:
        """Загружает текущий домен из файла пользователя"""
        try:
            user_id = st.session_state.get('user_id')

            if 'domain_manager' not in st.session_state:
                st.session_state.domain_manager = DomainManager()

            dm = st.session_state.domain_manager

            if user_id:
                settings = dm.load_user_settings(user_id)
                saved_domain = settings.get('selected_domain', 'default')
                saved_site = settings.get('selected_site', 'steelborg')

                # Обновляем session_state
                st.session_state.current_domain = saved_domain
                st.session_state.selected_domain = saved_domain
                st.session_state.current_site = saved_site
                st.session_state.selected_site = saved_site
                st.session_state[f'domain_system_{saved_site}'] = saved_domain

                return saved_site, saved_domain
        except Exception as e:
            print(f"⚠️ FileDataManager: ошибка загрузки домена: {e}")

        # Fallback
        return st.session_state.get('current_site', 'steelborg'), st.session_state.get('current_domain', 'default')

    def get_project_path(self, project_id: str = None) -> tuple[Path, Dict]:
        """Возвращает путь к файлу проекта и загруженные данные"""
        user_id = st.session_state.get('user_id')

        # ✅ ЗАГРУЖАЕМ ДОМЕН ИЗ ФАЙЛА
        site, domain = self._get_current_domain()

        # --- ИСПРАВЛЕНИЕ: если project_id не передан, БЕРЕМ ИЗ ПАРАМЕТРА ---
        if not project_id:
            project_id = st.session_state.get('current_project_id')

        if not project_id or not user_id:
            return None, None

        project_file = Path(f"sites/{site}/domains/{domain}/projects/{user_id}/{project_id}.json")

        if not project_file.exists():
            return project_file, None

        try:
            with open(project_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return project_file, data
        except:
            return project_file, None

    def save_phase4_prompts(self, prompts: List[Dict], project_id: str = None) -> bool:
        """ПРЯМОЕ сохранение промптов фазы 4 в файл"""
        project_file, data = self.get_project_path(project_id)

        if not project_file:
            print("❌ Нет активного проекта")
            return False

        if data is None:
            site, domain = self._get_current_domain()
            data = {
                "project_id": project_id or st.session_state.get('current_project_id'),
                "user_id": st.session_state.get('user_id'),
                "site_name": site,
                "domain_name": domain,
                "app_data": {}
            }

        # Сохраняем промпты
        if 'app_data' not in data:
            data['app_data'] = {}

        data['app_data']['phase4'] = {
            'prompts': prompts,
            'generated_count': len(prompts),
            'generated_at': datetime.now().isoformat()
        }

        # Дублируем для обратной совместимости
        data['app_data']['phase4_generated_prompts'] = prompts

        data['updated_at'] = datetime.now().isoformat()

        # Пишем напрямую в файл
        try:
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ Phase4 сохранены: {len(prompts)} промптов")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False

    def save_phase5_results(self, results: Dict, statistics: Dict = None, project_id: str = None) -> bool:
        """ПРЯМОЕ сохранение результатов фазы 5 в файл"""
        project_file, data = self.get_project_path(project_id)

        if not project_file:
            print("❌ Нет активного проекта")
            return False

        if data is None:
            site, domain = self._get_current_domain()
            data = {
                "project_id": project_id or st.session_state.get('current_project_id'),
                "user_id": st.session_state.get('user_id'),
                "site_name": site,
                "domain_name": domain,
                "app_data": {}
            }

        if 'app_data' not in data:
            data['app_data'] = {}

        data['app_data']['phase5'] = {
            'results': results,
            'statistics': statistics or {
                'total': len(results),
                'success': sum(1 for r in results.values() if r.get('status') == 'success'),
                'error': sum(1 for r in results.values() if r.get('status') == 'error'),
                'pending': 0
            },
            'phase_completed': True,
            'completed_at': datetime.now().isoformat()
        }
        data['app_data']['phase5_completed'] = True
        data['app_data']['phase5_results'] = results
        data['updated_at'] = datetime.now().isoformat()

        try:
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ Phase5 сохранены: {len(results)} результатов")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False

    def save_phase6_results(self, processed_texts: List[str], replacements: List[Dict],
                            original_texts: List[str], metadata: List[Dict], project_id: str = None) -> bool:
        """ПРЯМОЕ сохранение результатов фазы 6 в файл"""
        project_file, data = self.get_project_path(project_id)

        if not project_file:
            print("❌ Нет активного проекта")
            return False

        if data is None:
            site, domain = self._get_current_domain()
            data = {
                "project_id": project_id or st.session_state.get('current_project_id'),
                "user_id": st.session_state.get('user_id'),
                "site_name": site,
                "domain_name": domain,
                "app_data": {}
            }

        if 'app_data' not in data:
            data['app_data'] = {}

        # Формируем результаты для фазы 7
        results = {}
        for idx, text in enumerate(processed_texts):
            meta = metadata[idx] if idx < len(metadata) else {}
            prompt_id = meta.get('prompt_id', f"synonymized_{idx}")
            results[prompt_id] = {
                'prompt_id': prompt_id,
                'edited_text': text,
                'ai_response': text,
                'status': 'success',
                'characteristic_name': meta.get('characteristic_name', ''),
                'characteristic_value': meta.get('characteristic_value', ''),
                'type': meta.get('type', 'synonymized'),
                'original_text': original_texts[idx] if idx < len(original_texts) else ''
            }

        data['app_data']['phase6'] = {
            'processed_texts': processed_texts,
            'original_texts': original_texts,
            'replacements': replacements,
            'texts_metadata': metadata,
            'results': results,
            'statistics': {
                'total_texts': len(processed_texts),
                'total_replacements': len(replacements)
            },
            'phase_completed': True,
            'completed_at': datetime.now().isoformat()
        }
        data['app_data']['phase6_completed'] = True
        data['updated_at'] = datetime.now().isoformat()

        try:
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ Phase6 сохранены: {len(processed_texts)} текстов")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False

    def load_phase4_prompts(self, project_id: str = None) -> List[Dict]:
        """ПРЯМАЯ загрузка промптов из файла"""
        _, data = self.get_project_path(project_id)

        if not data:
            return []

        # Пробуем разные места хранения
        phase4 = data.get('app_data', {}).get('phase4', {})
        if phase4.get('prompts'):
            return phase4['prompts']

        if data.get('app_data', {}).get('phase4_generated_prompts'):
            return data['app_data']['phase4_generated_prompts']

        return []

    def load_phase5_results(self, project_id: str = None) -> Dict:
        """ПРЯМАЯ загрузка результатов из файла"""
        _, data = self.get_project_path(project_id)

        if not data:
            return {}

        phase5 = data.get('app_data', {}).get('phase5', {})
        if phase5.get('results'):
            return phase5['results']

        if data.get('app_data', {}).get('phase5_results'):
            return data['app_data']['phase5_results']

        return {}

    def load_phase6_results(self, project_id: str = None) -> Dict:
        """ПРЯМАЯ загрузка результатов фазы 6 из файла"""
        _, data = self.get_project_path(project_id)

        if not data:
            return {}

        phase6 = data.get('app_data', {}).get('phase6', {})
        return phase6

    def delete_phase_data(self, phase: int, project_id: str = None) -> bool:
        """Удаление данных конкретной фазы (по кнопке перезапуска)"""
        project_file, data = self.get_project_path(project_id)

        if not project_file or not data:
            return False

        if 'app_data' not in data:
            data['app_data'] = {}

        # Удаляем данные фазы
        data['app_data'][f'phase{phase}'] = {}

        # Специальные случаи
        if phase == 5:
            data['app_data']['phase5_completed'] = False
            data['app_data']['phase5_results'] = {}
        elif phase == 6:
            data['app_data']['phase6_completed'] = False
        elif phase == 7:
            data['app_data']['phase7'] = {}
            data['app_data']['phase7_completed'] = False

        data['updated_at'] = datetime.now().isoformat()

        try:
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ Данные фазы {phase} удалены")
            return True
        except Exception as e:
            print(f"❌ Ошибка удаления: {e}")
            return False

    def _create_empty_project_data(self, project_id: str = None) -> Dict:
        """Создаёт пустую структуру проекта"""
        site, domain = self._get_current_domain()
        return {
            "project_id": project_id or st.session_state.get('current_project_id'),
            "project_name": st.session_state.get('app_data', {}).get('project_name', 'Новый проект'),
            "category": st.session_state.get('app_data', {}).get('category', ''),
            "user_id": st.session_state.get('user_id'),
            "site_name": site,
            "domain_name": domain,
            "current_phase": 1,
            "app_data": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

    def is_phase5_completed(self, project_id: str = None) -> bool:
        """Проверяет, завершена ли фаза 5 (по файлу)"""
        _, data = self.get_project_path(project_id)

        if not data:
            return False

        # Проверяем по наличию результатов
        if data.get('app_data', {}).get('phase5', {}).get('results'):
            return True
        if data.get('app_data', {}).get('phase5_results'):
            return True
        if data.get('app_data', {}).get('phase5_completed'):
            return True

        return False