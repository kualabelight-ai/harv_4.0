import json
import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import os

def parse_json_v2(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # === 1. Общая информация о проекте ===
    project_info = {
        'project_id': data.get('project_id', ''),
        'project_name': data.get('project_name', ''),
        'category': data.get('category', ''),
        'current_phase': data.get('current_phase', ''),
        'site_name': data.get('site_name', ''),
        'domain_name': data.get('domain_name', ''),
        'created_at': data.get('created_at', ''),
        'updated_at': data.get('updated_at', ''),
    }

    app_data = data.get('app_data', {})

    # === 2. Характеристики из phase1 ===
    chars_data = []
    phase1 = app_data.get('phase1', {})
    characteristics = phase1.get('characteristics', [])

    for char in characteristics:
        char_id = char.get('char_id', '')
        char_name = char.get('char_name', '')
        original_name = char.get('original_name', '')
        unit = char.get('unit', '')
        is_unique = char.get('is_unique', False)
        is_duplicate = char.get('is_duplicate', False)

        values = char.get('values', [])
        if values:
            for val in values:
                chars_data.append({
                    'char_id': char_id,
                    'char_name': char_name,
                    'original_name': original_name,
                    'unit': unit,
                    'is_unique': is_unique,
                    'is_duplicate': is_duplicate,
                    'value': val.get('value', ''),
                    'items_count': val.get('items_count', 0),
                    'offers_sum': val.get('offers_sum', 0),
                    'percent': val.get('percent', 0),
                })
        else:
            chars_data.append({
                'char_id': char_id,
                'char_name': char_name,
                'original_name': original_name,
                'unit': unit,
                'is_unique': is_unique,
                'is_duplicate': is_duplicate,
                'value': '',
                'items_count': 0,
                'offers_sum': 0,
                'percent': 0,
            })

    # === 3. Промпты из phase4 ===
    prompts_data = []
    phase4 = app_data.get('phase4', {})
    prompts = phase4.get('prompts', [])

    for prompt in prompts:
        # Определяем тип: характеристика или блок
        prompt_type = prompt.get('type', 'unknown')
        characteristic_id = prompt.get('characteristic_id', '')
        characteristic_name = prompt.get('characteristic_name', '')
        block_id = prompt.get('block_id', '')
        block_name = prompt.get('block_name', '')
        value = prompt.get('value', '')

        prompts_data.append({
            'тип': 'характеристика' if characteristic_id else 'блок',
            'characteristic_id': characteristic_id,
            'characteristic_name': characteristic_name,
            'block_id': block_id,
            'block_name': block_name,
            'value': value,
            'prompt_num': prompt.get('prompt_num', ''),
            'prompt_text': prompt.get('prompt', '')[:500] + '...' if len(prompt.get('prompt', '')) > 500 else prompt.get('prompt', ''),
            'unresolved_variables': str(prompt.get('unresolved_variables', [])),
        })

    # === 4. Результаты генерации из phase5 ===
    results_data = []
    phase5 = app_data.get('phase5', {})
    results = phase5.get('results', {})

    for key, result in results.items():
        # Извлекаем информацию из ключа (формат: char_XXXXX_value_num)
        parts = key.split('_')
        char_id = parts[1] if len(parts) > 1 else ''
        value = parts[2] if len(parts) > 2 else ''
        prompt_num = parts[3] if len(parts) > 3 else ''

        results_data.append({
            'key': key,
            'char_id': char_id,
            'value': value,
            'prompt_num': prompt_num,
            'characteristic_name': result.get('characteristic_name', ''),
            'characteristic_value': result.get('characteristic_value', ''),
            'block_name': result.get('block_name', ''),
            'type': result.get('type', ''),
            'status': result.get('status', ''),
            'model': result.get('model', ''),
            'tokens_used': result.get('tokens_used', 0),
            'ai_response': result.get('ai_response', '')[:1000] + '...' if len(result.get('ai_response', '')) > 1000 else result.get('ai_response', ''),
            'edited_text': result.get('edited_text', '')[:1000] + '...' if len(result.get('edited_text', '')) > 1000 else result.get('edited_text', ''),
            'error_message': result.get('error_message', ''),
            'generated_at': result.get('generated_at', ''),
        })

    # === 5. Статистика phase5 ===
    stats = phase5.get('statistics', {})
    stats_data = [{
        'total': stats.get('total', 0),
        'success': stats.get('success', 0),
        'error': stats.get('error', 0),
        'completed': stats.get('completed', 0),
        'pending': stats.get('pending', 0),
        'selected': stats.get('selected', 0),
        'generated_at': phase5.get('generated_at', ''),
        'prompts_count': phase5.get('prompts_count', 0),
    }]

    return project_info, chars_data, prompts_data, results_data, stats_data

def main():
    root = tk.Tk()
    root.withdraw()

    json_path = filedialog.askopenfilename(
        title='Выберите JSON-файл с данными проекта',
        filetypes=[('JSON files', '*.json'), ('All files', '*.*')]
    )
    if not json_path:
        messagebox.showinfo('Отмена', 'Файл не выбран.')
        return

    try:
        project_info, chars_data, prompts_data, results_data, stats_data = parse_json_v2(json_path)

        # Создаем DataFrame'ы
        df_project = pd.DataFrame([project_info])
        df_chars = pd.DataFrame(chars_data)
        df_prompts = pd.DataFrame(prompts_data)
        df_results = pd.DataFrame(results_data)
        df_stats = pd.DataFrame(stats_data)

        # Диалог сохранения
        default_name = os.path.splitext(os.path.basename(json_path))[0] + '_анализ.xlsx'
        save_path = filedialog.asksaveasfilename(
            title='Сохранить результат как',
            defaultextension='.xlsx',
            filetypes=[('Excel files', '*.xlsx')],
            initialfile=default_name
        )
        if not save_path:
            messagebox.showinfo('Отмена', 'Сохранение отменено.')
            return

        # Сохраняем в Excel с несколькими листами
        with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
            df_project.to_excel(writer, sheet_name='Проект', index=False)
            df_chars.to_excel(writer, sheet_name='Характеристики', index=False)
            df_prompts.to_excel(writer, sheet_name='Промпты', index=False)
            df_results.to_excel(writer, sheet_name='Результаты_генерации', index=False)
            df_stats.to_excel(writer, sheet_name='Статистика', index=False)

            # Автоподгонка ширины для всех листов
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for col in worksheet.columns:
                    max_length = 0
                    column_letter = col[0].column_letter
                    for cell in col:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 60)
                    worksheet.column_dimensions[column_letter].width = adjusted_width

        messagebox.showinfo('Готово', f'Анализ сохранён в:\n{save_path}\n\nЛисты:\n- Проект (общая информация)\n- Характеристики (значения и статистика)\n- Промпты (все запросы)\n- Результаты генерации (сгенерированные тексты)\n- Статистика (общие цифры)')

    except Exception as e:
        messagebox.showerror('Ошибка', f'При обработке произошла ошибка:\n{str(e)}')

if __name__ == '__main__':
    main()