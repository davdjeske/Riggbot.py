"""Tests for logging format, storage and messaging helpers."""
import json
import logging
from unittest.mock import AsyncMock

import pytest

from riggbot.config import LoggingSettings
from riggbot.log import RiggFormatter, component_name, setup_logging
from riggbot.messaging import split_message
from riggbot.storage import GuildStore, JsonStore, read_default
from riggbot.ui.pagination import Paginator, build_pages

from .conftest import make_interaction, make_user


def make_record(name='riggbot.translation', level=logging.INFO, msg='hello'):
    record = logging.LogRecord(name, level, __file__, 1, msg, None, None)
    record.created = 1790000000.123
    record.msecs = 123
    return record


class TestLogFormat:
    def test_plain_format(self):
        line = RiggFormatter(color=False).format(make_record())
        date, time_, level, component, message = line.split(' ', 4)
        assert len(date) == 10 and len(time_) == 12 and time_.endswith('.123')
        assert (level, component, message) == ('[info]', '[translation]', 'hello')

    def test_newlines_are_escaped(self):
        line = RiggFormatter().format(make_record(msg='a\nb'))
        assert '\n' not in line and line.endswith('a\\nb')

    def test_colors(self):
        line = RiggFormatter(color=True).format(make_record(level=logging.DEBUG))
        assert '\x1b[90m' in line          # gray timestamp
        assert '\x1b[36m[debug]' in line   # cyan debug
        info = RiggFormatter(color=True).format(make_record(level=logging.INFO))
        assert '\x1b[34m[info]' in info    # blue info

    @pytest.mark.parametrize('name, expected', [
        ('riggbot.cogs.translate', 'cogs.translate'),
        ('riggbot', 'core'),
        ('discord.gateway', 'discord.gateway'),
    ])
    def test_component_name(self, name, expected):
        assert component_name(name) == expected

    def test_setup_writes_file_without_colors(self, tmp_path):
        settings = LoggingSettings(color='always', file='logs/test.log', file_level='DEBUG')
        setup_logging(settings, tmp_path)
        try:
            logging.getLogger('riggbot.test').debug('to the file')
            for handler in logging.getLogger().handlers:
                handler.flush()
            content = (tmp_path / 'logs' / 'test.log').read_text(encoding='utf-8')
            assert '[debug] [test] to the file' in content
            assert '\x1b[' not in content
        finally:
            root = logging.getLogger()
            for handler in [h for h in root.handlers if getattr(h, '_riggbot', False)]:
                root.removeHandler(handler)
                handler.close()


class TestJsonStore:
    async def test_starts_from_initial_and_saves(self, tmp_path):
        store = JsonStore(tmp_path / 'data' / 'map.json', initial=lambda: {'a': 1})
        assert store.data == {'a': 1}
        store.data['b'] = 2
        await store.save()
        assert json.loads((tmp_path / 'data' / 'map.json').read_text(encoding='utf-8')) == {'a': 1, 'b': 2}
        assert JsonStore(tmp_path / 'data' / 'map.json').data == {'a': 1, 'b': 2}

    def test_corrupt_file_is_moved_aside(self, tmp_path):
        path = tmp_path / 'map.json'
        path.write_text('{not json', encoding='utf-8')
        store = JsonStore(path, initial=dict)
        assert store.data == {}
        assert not path.exists()
        assert len(list(tmp_path.glob('map.json.corrupt-*'))) == 1

    def test_wrong_type_is_moved_aside(self, tmp_path):
        path = tmp_path / 'map.json'
        path.write_text('[1, 2]', encoding='utf-8')
        assert JsonStore(path, initial=dict).data == {}


class TestGuildStore:
    async def test_sections_are_per_guild_and_persist(self, tmp_path):
        store = GuildStore(tmp_path)
        store.section(1, 'items', list).append('one')
        assert store.section(2, 'items', list) == []
        await store.save(1)

        fresh = GuildStore(tmp_path)
        assert fresh.section(1, 'items', list) == ['one']
        assert fresh.section(1, 'other', lambda: {'x': 1}) == {'x': 1}
        assert not (tmp_path / '2.json').exists()

    async def test_reload_rereads_disk(self, tmp_path):
        store = GuildStore(tmp_path)
        store.section(1, 'items', list).append('unsaved')
        store.reload()
        assert store.section(1, 'items', list) == []


def test_read_default_returns_copies():
    first = read_default('flag_lang_map.json')
    first['🇺🇸'] = 'changed'
    assert read_default('flag_lang_map.json')['🇺🇸'] == 'en'


class TestSplitMessage:
    def test_short_text_is_one_chunk(self):
        assert split_message('hi\nthere') == ['hi\nthere']

    def test_splits_between_lines(self):
        text = '\n'.join(['x' * 900] * 3)
        chunks = split_message(text)
        assert chunks == ['x' * 900 + '\n' + 'x' * 900, 'x' * 900]

    def test_hard_splits_long_lines(self):
        chunks = split_message('y' * 4500)
        assert [len(c) for c in chunks] == [2000, 2000, 500]

    def test_all_chunks_within_limit(self):
        text = '\n'.join(('word ' * n) for n in range(1, 400))
        assert all(len(c) <= 2000 for c in split_message(text))
        assert ''.join(split_message(text)).replace('\n', '') == text.replace('\n', '')


class TestPaginator:
    async def test_only_the_command_user_can_flip_pages(self):
        view = Paginator(['a', 'b', 'c'], user_id=1)
        assert view.previous.disabled and not view.next.disabled

        stranger = make_interaction(user=make_user(user_id=2))
        assert await view.interaction_check(stranger) is False
        assert stranger.response.send_message.call_args.kwargs['ephemeral'] is True

        owner = make_interaction(user=make_user(user_id=1))
        owner.response.edit_message = AsyncMock()
        assert await view.interaction_check(owner) is True
        await view.next.callback(owner)
        assert view.index == 1 and owner.response.edit_message.call_args.kwargs['content'] == 'b\n-# Page 2/3'
        await view.next.callback(owner)
        assert view.next.disabled

    async def test_respond_single_page_has_no_buttons(self):
        interaction = make_interaction()
        await Paginator.respond(interaction, ['only'])
        assert 'view' not in interaction.response.send_message.call_args.kwargs


class TestBuildPages:
    def test_line_limit(self):
        pages = build_pages([str(i) for i in range(40)], title='T', max_lines=15)
        assert len(pages) == 3
        assert all(page.startswith('T\n') for page in pages)
        assert pages[2].count('\n') == 10   # title + 10 lines

    def test_char_limit(self):
        pages = build_pages(['a' * 60] * 10, max_chars=200, max_lines=100)
        assert all(len(page) <= 200 for page in pages)
        assert sum(page.count('a' * 60) for page in pages) == 10

    def test_truncates_huge_line(self):
        (page,) = build_pages(['z' * 5000], max_chars=100)
        assert len(page) <= 100 and page.endswith('…')

    def test_empty(self):
        assert build_pages([]) == []
