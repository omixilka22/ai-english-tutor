"""Manual transcript upload, four-block review and explicit teacher approval."""
import asyncio
from aiogram import F, Router
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.exc import SQLAlchemyError
from app.bot.ui import clear_flow, show_screen, navigation, keyboard, paginated_screen
from app.database.database import AsyncSessionLocal
from app.services import material_service as service
from app.services.analysis_content import (BLOCKS, MAX_FILE_BYTES, LimitedBuffer, decode_transcript,
                                           validate_transcript)
from app.services.calendar_service import CalendarService, utcnow
from datetime import timedelta

router = Router(name='materials')
ERRORS = {
    'pdf_dependency_missing': 'Для створення PDF встановіть залежність: python -m pip install -r requirements-pdf.txt. Потім перезапустіть бота й повторіть надсилання.',
    'pdf_generation_failed': 'Не вдалося сформувати PDF. Перевірте наявність шрифтів у app/assets/fonts. Матеріали збережено.',
    'invalid_request': 'Gemini відхилив запит (HTTP 400). Перевірте формат запиту, ключ API та підтримку моделі.',
    'provider_unavailable': 'Сервіс Gemini тимчасово недоступний (HTTP 5xx). Спробуйте пізніше.',
    'provider_error': 'Gemini відхилив HTTP-запит. Потрібна перевірка відповіді API; транскрипт збережено.',
    'missing_transcript': 'Текст транскрипту не знайдено в базі. Потрібна перевірка запису заняття.',
    'missing_key': 'Не налаштовано GEMINI_API_KEY. Додайте ключ у .env, перезапустіть бота й повторіть аналіз.',
    'invalid_model': 'Перевірте GEMINI_MODEL у .env.',
    'credentials': 'Gemini не прийняв ключ або доступ до API. Перевірте налаштування.',
    'model_unavailable': 'Модель Gemini недоступна. Перевірте GEMINI_MODEL.',
    'quota': 'Вичерпано квоту Gemini. Перевірте квоту й повторіть пізніше.',
    'network': 'Не вдалося дочекатися Gemini. Повторіть аналіз пізніше.',
    'invalid_response': 'Gemini повернув неповний або некоректний аналіз. Спробуйте ще раз.',
    'delivery_failed': 'Не вдалося доставити матеріали. Учень може відкрити їх у меню. Перед повтором перевірте, чи файл уже прийшов.',
}

for _status in range(500, 600):
    ERRORS[f'http_{_status}'] = (f'Gemini повернув HTTP {_status}. '
        + ('Модель перевантажена або тимчасово недоступна.' if _status == 503 else 'Помилка сервера під час обробки запиту.')
        + ' Транскрипт збережено. Якщо помилка повторюється, перевірте модель командою python -m app.check_gemini --probe.')


class MaterialInput(StatesGroup):
    transcript = State()
    confirm = State()
    block = State()


def label(lesson):
    from zoneinfo import ZoneInfo
    return lesson.scheduled_at.astimezone(ZoneInfo(lesson.timezone)).strftime('%d.%m.%Y · %H:%M')


@router.callback_query(F.data.regexp(r'^materials_\d+$') | (F.data == 'my_materials'))
async def listing(callback, state):
    await callback.answer()
    await clear_flow(state)
    student_id = None if callback.data == 'my_materials' else int(callback.data.rsplit('_', 1)[1])
    async with AsyncSessionLocal() as session:
        try:
            student, teacher, lessons = await service.list_materials(session, callback.from_user.id, student_id)
        except ValueError as error:
            await show_screen(callback, state, str(error))
            return
    await paginated_screen(callback, state,
        '📖 Минулі заняття · проведення підтверджує викладач' if lessons else '📖 Матеріалів поки немає.' +
        (' Завершені заняття з’являться тут.' if teacher else 'Вони з’являться після підтвердження викладачем.'),
        rows=[[(('✓ ' if getattr(lesson, 'conducted_at', None) else '○ ') + label(lesson), f'material_{lesson.id}')] for lesson in lessons],
        footer=navigation(f'student_{student.id}' if teacher else 'home'))


async def render(event, state, lesson_id, page=0):
    async with AsyncSessionLocal() as session:
        try:
            lesson, teacher, analysis = await service.get_material(session, event.from_user.id, lesson_id)
        except ValueError as error:
            await show_screen(event, state, str(error))
            return
    back = f'materials_{lesson.student_id}' if teacher else 'my_materials'
    rows = []
    text = f'📖 Матеріали уроку · {label(lesson)}\n\n'
    if teacher and not getattr(lesson, 'conducted_at', None):
        text += 'Проведення уроку ще не підтверджене. Минула дата не означає, що заняття відбулося.'
        if lesson.scheduled_at + timedelta(minutes=lesson.duration_minutes) <= utcnow():
            rows += [[('✓ Урок проведено', f'attendance_yes_{lesson_id}')],
                     [('Урок не відбувся', f'attendance_no_{lesson_id}')]]
        else:
            text += '\nПідтвердження стане доступним після завершення запланованого часу.'
        rows.append([('‹ До списку', back), ('⌂ Головне меню', 'home')])
        await show_screen(event, state, text, reply_markup=keyboard(rows))
        return
    if analysis is None:
        text += 'Додайте транскрипт завершеного заняття: текст або .txt-файл.'
        if teacher:
            rows.append([('＋ Додати транскрипт', f'transcript_{lesson_id}')])
    elif analysis.workflow_state in ('review', 'approved', 'send_failed', 'sent'):
        page = min(max(page, 0), 3)
        key = list(BLOCKS)[page]
        text += f'{page + 1}/4 · {BLOCKS[key]}\n\n{analysis.content.get(key, "Блок відсутній.")}'
        arrows = []
        if page:
            arrows.append(('‹ Попередній блок', f'material_page_{lesson_id}_{page-1}'))
        if page < 3:
            arrows.append(('Наступний блок ›', f'material_page_{lesson_id}_{page+1}'))
        if arrows:
            rows.append(arrows)
        if teacher and analysis.workflow_state == 'review':
            text += '\n\nЧернетка: перевірте точність перед надсиланням.'
            rows.append([('✎ Редагувати блок', f'material_edit_{lesson_id}_{analysis.revision}_{page}')])
            if page == 3:
                rows.append([('✓ Підтвердити й надіслати', f'material_approve_{lesson_id}_{analysis.revision}')])
        elif teacher:
            text += '\n\n' + ('✓ Надіслано учню.' if analysis.workflow_state == 'sent' else
                              ERRORS.get(analysis.last_error, ERRORS['delivery_failed']) if analysis.workflow_state == 'send_failed' else 'Очікує надсилання учню.')
            if analysis.workflow_state == 'send_failed':
                rows.append([('Повторити надсилання', f'material_retry_{lesson_id}_{analysis.revision}')])
    elif analysis.workflow_state == 'queued':
        text += '⏳ Транскрипт збережено. Аналіз у черзі або обробляється. Коли буде готово, ви отримаєте повідомлення.'
        rows.append([('Оновити', f'material_{lesson_id}')])
    elif analysis.workflow_state == 'failed':
        text += ERRORS.get(analysis.last_error, 'Не вдалося виконати аналіз. Транскрипт збережено. Спробуйте ще раз.')
        rows.append([('Повторити аналіз', f'material_retry_{lesson_id}_{analysis.revision}')])
    else:
        text += 'Матеріали недоступні для цього процесу. Перевірте заняття та прив’язку учня до викладача.'
    rows.append([('‹ До списку', back), ('⌂ Головне меню', 'home')])
    await show_screen(event, state, text, reply_markup=keyboard(rows))


@router.callback_query(F.data.regexp(r'^(material|notification_material)_\d+$'))
@router.callback_query(F.data.regexp(r'^material_page_\d+_[0-3]$'))
async def detail(callback, state):
    await callback.answer()
    await clear_flow(state)
    parts = callback.data.split('_')
    paged = callback.data.startswith('material_page_')
    await render(callback, state, int(parts[-2] if paged else parts[-1]), int(parts[-1]) if paged else 0)


@router.callback_query(F.data.regexp(r'^transcript_\d+$'))
async def begin_upload(callback, state):
    await callback.answer()
    lesson_id = int(callback.data.rsplit('_', 1)[1])
    async with AsyncSessionLocal() as session:
        try:
            lesson, _, analysis = await service.get_material(session, callback.from_user.id, lesson_id, write=True)
            service.require_conducted(lesson)
            if analysis is not None:
                raise ValueError('Транскрипт уже додано. Відкрийте матеріали заняття.')
        except ValueError as error:
            await show_screen(callback, state, str(error), reply_markup=navigation(f'material_{lesson_id}'))
            return
    await clear_flow(state)
    await state.update_data(material_lesson_id=lesson_id, transcript_text='')
    await state.set_state(MaterialInput.transcript)
    await show_screen(callback, state,
        'Надішліть транскрипт текстом (можна кількома повідомленнями) або .txt у UTF-8, до 256 КБ / 60 000 символів.\n\n'
        'Після додавання натисніть «Завершити». Підтверджений текст буде передано Gemini для аналізу.',
        reply_markup=navigation(f'material_{lesson_id}'))


@router.message(MaterialInput.transcript)
async def receive(callback_message, state):
    message = callback_message
    data = await state.get_data()
    lesson_id = data['material_lesson_id']
    try:
        # Recheck ownership before downloading private Telegram files.
        async with AsyncSessionLocal() as session:
            await CalendarService.lesson_access(session, message.from_user.id, lesson_id, write=True)
        if message.document:
            doc = message.document
            if not (doc.file_name or '').lower().endswith('.txt'):
                raise ValueError('Потрібен .txt-файл у UTF-8.')
            if doc.file_size is not None and doc.file_size > MAX_FILE_BYTES:
                raise ValueError('Файл завеликий. Максимум — 256 КБ.')
            buffer = LimitedBuffer()
            await asyncio.wait_for(message.bot.download(doc, destination=buffer), timeout=30)
            fragment = decode_transcript(buffer.getvalue())
        elif message.text:
            fragment = validate_transcript(message.text)
        else:
            raise ValueError('Надішліть текст або .txt-файл.')
        text = validate_transcript('\n\n'.join(filter(None, [data.get('transcript_text'), fragment])))
    except (ValueError, TimeoutError) as error:
        text_error = str(error) if isinstance(error, ValueError) else 'Не вдалося завантажити файл. Спробуйте ще раз.'
        await show_screen(message, state, text_error, reply_markup=navigation(f'material_{lesson_id}'))
        return
    except Exception:
        await show_screen(message, state, 'Не вдалося отримати файл. Спробуйте ще раз.', reply_markup=navigation(f'material_{lesson_id}'))
        return
    await state.update_data(transcript_text=text)
    await show_screen(message, state, f'Додано {len(text)} символів. Можна надіслати наступну частину або завершити.',
        reply_markup=keyboard([[('✓ Завершити', 'transcript_finish')], [('‹ Скасувати', f'material_{lesson_id}')], [('⌂ Головне меню', 'home')]]))


@router.callback_query(MaterialInput.transcript, F.data == 'transcript_finish')
async def finish(callback, state):
    await callback.answer()
    data = await state.get_data()
    if not data.get('transcript_text'):
        return
    await state.set_state(MaterialInput.confirm)
    await show_screen(callback, state, f"Зберегти й проаналізувати {len(data['transcript_text'])} символів?\n\n"
        + data['transcript_text'][:700] + '\n\nТекст буде передано Gemini. Учень отримає лише матеріали, які ви підтвердите.',
        reply_markup=keyboard([[('✓ Проаналізувати', 'transcript_confirm')], [('‹ Додати ще текст', 'transcript_more')],
                               [('Скасувати', f"material_{data['material_lesson_id']}")], [('⌂ Головне меню', 'home')]]))


@router.callback_query(MaterialInput.confirm, F.data == 'transcript_more')
async def more(callback, state):
    await callback.answer()
    await state.set_state(MaterialInput.transcript)
    data = await state.get_data()
    await show_screen(callback, state, 'Надішліть наступну частину транскрипту.', reply_markup=keyboard([
        [('✓ Завершити', 'transcript_finish')], [('‹ Скасувати', f"material_{data['material_lesson_id']}")]]))


@router.callback_query(MaterialInput.confirm, F.data == 'transcript_confirm')
async def confirm_upload(callback, state):
    await callback.answer()
    data = await state.get_data()
    lesson_id = data['material_lesson_id']
    async with AsyncSessionLocal() as session:
        try:
            await service.upload(session, callback.from_user.id, lesson_id, data['transcript_text'])
        except (ValueError, SQLAlchemyError) as error:
            await session.rollback()
            await show_screen(callback, state, str(error) if isinstance(error, ValueError) else 'Не вдалося зберегти. Спробуйте ще раз.',
                              reply_markup=keyboard([[('Повторити', 'transcript_confirm')], [('‹ До матеріалів', f'material_{lesson_id}')]]))
            return
    await clear_flow(state)
    await render(callback, state, lesson_id)


@router.callback_query(F.data.regexp(r'^material_edit_\d+_\d+_[0-3]$'))
async def begin_edit(callback, state):
    await callback.answer()
    lesson_id, revision, page = map(int, callback.data.split('_')[-3:])
    async with AsyncSessionLocal() as session:
        try:
            lesson, _, analysis = await service.get_material(session, callback.from_user.id, lesson_id, write=True)
            service.require_conducted(lesson)
            service.check_revision(analysis, revision, {'review'})
        except ValueError as error:
            await show_screen(callback, state, str(error))
            return
    await clear_flow(state)
    await state.update_data(material_lesson_id=lesson_id, material_revision=revision, material_page=page)
    await state.set_state(MaterialInput.block)
    await show_screen(callback, state, f'Введіть новий текст блоку «{list(BLOCKS.values())[page]}» (до 2800 символів).',
                      reply_markup=navigation(f'material_page_{lesson_id}_{page}'))


@router.message(MaterialInput.block)
async def save_edit(message, state):
    data = await state.get_data()
    lesson_id, page = data['material_lesson_id'], data['material_page']
    async with AsyncSessionLocal() as session:
        try:
            await service.edit_block(session, message.from_user.id, lesson_id, data['material_revision'],
                                     list(BLOCKS)[page], message.text or '')
        except (ValueError, SQLAlchemyError) as error:
            await session.rollback()
            await show_screen(message, state, str(error) if isinstance(error, ValueError) else 'Зміни не збережено. Спробуйте ще раз.',
                              reply_markup=navigation(f'material_page_{lesson_id}_{page}'))
            return
    await clear_flow(state)
    await render(message, state, lesson_id, page)


@router.callback_query(F.data.regexp(r'^material_approve_\d+_\d+$'))
async def ask_approval(callback, state):
    await callback.answer()
    lesson_id, revision = map(int, callback.data.split('_')[-2:])
    async with AsyncSessionLocal() as session:
        try:
            lesson, _, analysis = await service.get_material(session, callback.from_user.id, lesson_id, write=True)
            service.require_conducted(lesson)
            service.check_revision(analysis, revision, {'review'})
        except ValueError as error:
            await show_screen(callback, state, str(error))
            return
    await clear_flow(state)
    await show_screen(callback, state, 'Ви перевірили всі чотири блоки?\n\nПісля підтвердження учень отримає повний PDF із матеріалами '
        'та зможе прочитати їх у боті. Редагування цієї версії буде закрито.', reply_markup=keyboard([
            [('✓ Надіслати учню', f'material_send_{lesson_id}_{revision}')],
            [('‹ Повернутися до перевірки', f'material_page_{lesson_id}_3')], [('⌂ Головне меню', 'home')]]))


@router.callback_query(F.data.regexp(r'^material_(send|retry)_\d+_\d+$'))
async def transition(callback, state):
    await callback.answer()
    lesson_id, revision = map(int, callback.data.split('_')[-2:])
    operation = service.approve if callback.data.startswith('material_send_') else service.retry
    async with AsyncSessionLocal() as session:
        try:
            await operation(session, callback.from_user.id, lesson_id, revision)
        except (ValueError, SQLAlchemyError) as error:
            await session.rollback()
            await show_screen(callback, state, str(error) if isinstance(error, ValueError) else 'Не вдалося зберегти дію. Спробуйте ще раз.',
                              reply_markup=navigation(f'material_{lesson_id}'))
            return
    await clear_flow(state)
    await render(callback, state, lesson_id)


@router.callback_query(F.data.in_({'transcript_finish', 'transcript_confirm', 'transcript_more'}))
async def stale(callback):
    await callback.answer('Цю дію вже завершено. Відкрийте матеріали знову.', show_alert=True)


@router.callback_query(F.data.regexp(r'^attendance_(yes|no)_\d+$'))
async def ask_attendance(callback, state):
    await callback.answer()
    lesson_id = int(callback.data.rsplit('_', 1)[1])
    async with AsyncSessionLocal() as session:
        try:
            await CalendarService.lesson_access(session, callback.from_user.id, lesson_id, write=True)
        except ValueError as error:
            await show_screen(callback, state, str(error))
            return
    await clear_flow(state)
    conducted = callback.data.startswith('attendance_yes_')
    text = ('Підтвердити, що ви провели цей урок? Після цього можна додати транскрипт.' if conducted else
            'Позначити, що урок не відбувся? Заняття буде скасоване, обробка матеріалів зупиниться. Щотижневий розклад не зміниться.')
    action = 'yes' if conducted else 'no'
    await show_screen(callback, state, text, reply_markup=keyboard([
        [('Підтвердити', f'attendance_save_{action}_{lesson_id}')],
        [('‹ Назад', f'material_{lesson_id}'), ('⌂ Головне меню', 'home')]]))


@router.callback_query(F.data.regexp(r'^attendance_save_(yes|no)_\d+$'))
async def save_attendance(callback, state):
    await callback.answer()
    lesson_id = int(callback.data.rsplit('_', 1)[1])
    conducted = callback.data.split('_')[-2] == 'yes'
    async with AsyncSessionLocal() as session:
        try:
            await service.confirm_attendance(session, callback.from_user.id, lesson_id, conducted=conducted)
        except (ValueError, SQLAlchemyError) as error:
            await session.rollback()
            await show_screen(callback, state, str(error) if isinstance(error, ValueError) else 'Не вдалося зберегти підтвердження.',
                              reply_markup=navigation(f'material_{lesson_id}'))
            return
    await clear_flow(state)
    if conducted:
        await render(callback, state, lesson_id)
    else:
        await show_screen(callback, state, 'Заняття позначено як таке, що не відбулося.', reply_markup=navigation(f'lesson_{lesson_id}'))
