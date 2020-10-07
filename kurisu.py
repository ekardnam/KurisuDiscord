#!/usr/bin/env python3.8

import asyncio
import discord
import environs
import googletrans
import gtts
import json
import os
import pykakasi
import random
import requests
import schedule
import threading
import time

from datetime import datetime, timedelta

def are_same_day(date1, date2):
    return (date1.replace(hour=0, minute=0, second=0, microsecond=0) - date2.replace(hour=0, minute=0, second=0, microsecond=0)).days == 0

def delete_if_exists(filename):
    try:
        os.unlink(filename)
    except FileNotFoundError:
        pass

def translate_italian_to_japanese(text):
    translator = googletrans.Translator()
    return translator.translate(text, src='it', dest='ja').text

def japanese_to_romaji(text):
    kakasi = pykakasi.kakasi()
    kakasi.setMode('H', 'a')
    kakasi.setMode('K', 'a')
    kakasi.setMode('J', 'a')
    kakasi.setMode('s', True)
    conv = kakasi.getConverter()
    return conv.do(text)

def create_voice(text, outfile, lang='ja'):
    tts = gtts.gTTS(text=text, lang=lang)
    tts.save(outfile)

class Scraper(object):
    def __init__(self, url):
        self.url = url
        self.dateformat = '%Y-%m-%dT%H:%M:%S'

    def scrape(self):
        res = requests.get(self.url)
        data = json.loads(res.text)
        now = datetime.now()
        return list(filter(lambda e: e['start'] > now, (map(lambda event: {
            'module_code': event['cod_modulo'],
            'start': datetime.strptime(event['start'], self.dateformat),
            'end': datetime.strptime(event['end'], self.dateformat),
            'title': event['title'],
            'teams_link': event['teams'],
            'note': event['note'],
            'prof': event['docente'],
            'time': event['time']
        }, data))))



class KurisuBot(discord.Client):
    def __init__(self, notify_channel, offset):
        super(KurisuBot, self).__init__()
        self.voice_client = None
        self.hour_offset = offset
        self.notify_channel = notify_channel
        self.first_year_scraper = Scraper('https://corsi.unibo.it/laurea/fisica/orario-lezioni/@@orario_reale_json?anno=1&curricula=')
        self.second_year_scraper = Scraper('https://corsi.unibo.it/laurea/fisica/orario-lezioni/@@orario_reale_json?anno=2&curricula=')
        self.third_year_scraper = Scraper('https://corsi.unibo.it/laurea/fisica/orario-lezioni/@@orario_reale_json?anno=3&curricula=')

        self.stop_event = threading.Event()

        self.quotes = [
            'I don\'t want to deny who I\'ve been. Because even my failures are a part of who I am today',
            'Something must be wrong for you to use my actual name',
            'Say it right, Hououin Pervert-Kyouma!',
            'People\'s feelings are memories that transcend time',
            'Who\'ll eat a pervert\'s banana anyway?',
            'It looks like you\'re both perverts',
            'There was a scientific rationale for that! Because... important memories, including, but not limited to, one\'s first kiss, are stored in the hippocampus, which makes them harder to forget',
            'Time is passing so quickly. Right now, I feel like complaining to Einstein. Whether time is slow or fast depends on perception. Relativity theory is so romantic. And so sad',
            'I\'ve only lived 18 years, but I don\'t want to change any of them. They\'re all part of my life, even the failures',
            'You\'ve pretty much figured it all out by now, right? That there is no absolute justice in this world. The opposite of justice is... another justice. Choosing the past through Time Leaps is just choosing between these justices. Can you say that your justice is correct?',
            '99.9% of science is boring'
        ]

        def scheduler_timer():
            while not self.stop_event.is_set():
                schedule.run_pending()
                time.sleep(10)
        self.scheduler_thread = threading.Thread(target=scheduler_timer)

    def _create_daily_embed(self, daily_events, channel):
        if not daily_events:
            return
        embed = discord.Embed()
        day = daily_events[0]['start'].strftime('%A')
        embed.add_field(name='Title', value=f'{day}\'s schedule', inline=False)
        for event in daily_events:
            title = event['title'].split('/')[0]
            embed.add_field(name='Course', value=title, inline=True)
            embed.add_field(name='Prof.', value=event['prof'], inline=True)
            embed.add_field(name='Time', value=event['time'], inline=True)
            embed.add_field(name='Teams', value=f'[Click!]({event["teams_link"]})', inline=False)
        return embed

    async def _play_audio(self, voice_channel, audio):
        if not self.voice_client or not self.voice_client.is_connected():
            self.voice_client = await voice_channel.connect()
        else:
            while self.voice_client.is_playing():
                await asyncio.sleep(1)
            if not self.voice_client.channel.name == voice_channel.name:
                await self.voice_client.move_to(voice_channel)
        self.voice_client.play(audio)

    async def _wait_if_playing(self):
        if self.voice_client:
            while self.voice_client.is_playing():
                await asyncio.sleep(1)

    async def _quote_command(self, channel, args, user):
        await channel.send(random.choice(self.quotes))

    async def _rus_command(self, channel, args, user):
        if len(args) < 2:
            await channel.send('Usage: -rus <sentence>')
            return
        if not user.voice:
            await channel.send('You have to be in a voice channel to use this command! BAKA')
            return
        voice_channel = user.voice.channel

        await self._wait_if_playing()

        delete_if_exists('audio.mp3')
        create_voice(' '.join(args[1:]), 'audio.mp3', lang='ru')
        await self._play_audio(voice_channel, discord.FFmpegPCMAudio('audio.mp3'))

    async def _jap_command(self, channel, args, user):
        if len(args) < 2:
            await channel.send('Usage: -jap <sentence>')
            return
        if not user.voice:
            await channel.send('You have to be in a voice channel to use this command! BAKA')
            return
        voice_channel = user.voice.channel

        await self._wait_if_playing()

        delete_if_exists('audio.mp3')
        create_voice(' '.join(args[1:]), 'audio.mp3')
        await self._play_audio(voice_channel, discord.FFmpegPCMAudio('audio.mp3'))

    async def _calendar_command(self, channel, args, user, scraper):
        events = scraper.scrape()
        days = 7
        if len(args) > 1:
            try:
                days = int(args[1])
            except ValueError:
                await channel.send('Usage: -calendar [number_of_days]')
                return
        await channel.send(f'Lectures of the next {days} days')
        now = datetime.now()
        then = now + timedelta(days=days)
        events = list(filter(lambda event: event['start'] < then, events))

        if not events:
            await channel.send('I didn\'t find any lessons')

        days_list = [now + timedelta(days=i) for i in range(days)]
        groups = [[e for e in events if are_same_day(e['start'], d)] for d in days_list]

        for group in groups:
            if group:
                await channel.send(embed=self._create_daily_embed(group, channel))

    async def _tj_command(self, channel, args, user):
        if len(args) < 2:
            await channel.send('Usage: -tj <sentence in italian>')
            return
        text = translate_italian_to_japanese(' '.join(args[1:]))
        await channel.send(f'Kanji: {text}\nRomaji: {japanese_to_romaji(text)}')

    async def _tjsay_command(self, channel, args, user):
        if len(args) < 2:
            await channel.send('Usage: -tjsay <sentence in italian>')
            return
        if not user.voice:
            await channel.send('You have to be in a voice channel BAKA')
            return
        voice_channel = user.voice.channel

        await self._wait_if_playing()

        delete_if_exists('audio.mp3')
        create_japanese_voice(translate_italian_to_japanese(' '.join(args[1:])), 'audio.mp3')
        await self._play_audio(voice_channel, discord.FFmpegPCMAudio('audio.mp3'))

    async def _kuristina_command(self, channel, args, user):
        if not user.voice:
            await channel.send('You have to be in a voice channel BAKA')
            return
        voice_channel = user.voice.channel
        await self._play_audio(voice_channel, discord.FFmpegPCMAudio('audio/KURISUTINA.mp3'))

    async def _tutturu_command(self, channel, args, user):
        if not user.voice:
            await channel.send('You have to be in a voice channel BAKA')
            return
        voice_channel = user.voice.channel
        tutturus = ['audio/OKARIN.mp3', 'audio/DESU.mp3']
        await self._play_audio(voice_channel, discord.FFmpegPCMAudio(random.choice(tutturus)))

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.content.startswith('-'):
            # got a command, parse it
            args = message.content.split(' ')
            if args[0] == '-quote':
                await self._quote_command(message.channel, args, message.author)

            if args[0] == '-calendar':
                if args[1] == 'first':
                    await self._calendar_command(message.channel, args, message.author, self.first_year_scraper)
                if args[1] == 'second':
                    await self._calendar_command(message.channel, args, message.author, self.second_year_scraper)
                if args[1] == 'third':
                    await self._calendar_command(message.channel, args, message.author, self.third_year_scraper)

            if args[0] == '-jap':
                await self._jap_command(message.channel, args, message.author)

            if args[0] == '-rus':
                await self._rus_command(message.channel, args, message.author)

            if args[0] == '-tj':
                await self._tj_command(message.channel, args, message.author)

            if args[0] == '-tjsay':
                await self._tjsay_command(message.channel, args, message.author)

            if args[0] == '-kuristina':
                await self._kuristina_command(message.channel, args, message.author)

            if args[0] == '-tutturu':
                await self._tutturu_command(message.channel, args, message.author)

    async def on_ready(self):
        print('Kurisu ready uwu')
        self._update_schedule()
        schedule.every().day.at('00:00').do(self._update_schedule)

    def _notify_lecture(self, event):
        embed = discord.Embed()
        title = event['title'].split('/')[0]
        embed.add_field(name='Course', value=title, inline=True)
        embed.add_field(name='Prof', value=event['prof'], inline=True)
        embed.add_field(name='Time', value=event['time'], inline=True)
        embed.add_field(name='Teams', value=f'[Click!]({event["teams_link"]})')
        asyncio.run_coroutine_threadsafe(self.get_channel(self.notify_channel).send(embed=embed), self.loop)
        asyncio.run_coroutine_threadsafe(self.get_channel(self.notify_channel).send('@everyone'), self.loop)

    def _update_schedule(self):
        print('Updating daily schedule')
        schedule.clear('daily_events')
        then = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_events = filter(lambda e: e['start'] < then, self.scraper.scrape())
        for event in daily_events:
            # this should really be done using UTC timestamps tbh
            hour = (event['start'] - timedelta(hours=self.hour_offset, minutes=10)).strftime('%H:%M')
            schedule.every().day.at(hour).do(
                self._notify_lecture, event
            ).tag('daily_events')
            print(f'Scheduled {event["title"]} at {hour}')

    def run(self, token):
        print('Starting Kurisu')
        self.scheduler_thread.start()
        if not discord.opus.is_loaded():
            discord.opus.load_opus('opus/lib/libopus.so.0')
        super(KurisuBot, self).run(token)


if __name__ == '__main__':
    env = environs.Env()
    env.read_env()
    kurisu = KurisuBot(int(env('NOTIFY_CHANNEL')), int(env('HOUR_OFFSET')))
    kurisu.run(env('DISCORD_TOKEN'))
