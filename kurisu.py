#!/usr/bin/env python3.8

import asyncio
import discord
import environs
import json
import random
import requests
import schedule
import threading
import time

from datetime import datetime, timedelta

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
            'room': event['aule'],
            'teams_link': event['teams'],
            'note': event['note'],
            'prof': event['docente'],
            'time': event['time']
        }, data['events']))))



class KurisuBot(discord.Client):
    def __init__(self, notify_channel):
        super(KurisuBot, self).__init__()
        self.notify_channel = notify_channel
        self.scraper = Scraper('https://corsi.unibo.it/laurea/fisica/orario-lezioni/@@orario_reale_json?anno=2&curricula=')

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

    async def _quote_command(self, channel, args):
        await channel.send(random.choice(self.quotes))

    async def _calendar_command(self, channel, args):
        events = self.scraper.scrape()
        days = 7
        if len(args) > 1:
            try:
                days = int(args[1])
            except ValueError:
                await channel.send('Usage: -calendar [number_of_days]')
                return
        await channel.send(f'Lectures of the next {days} days')
        then = datetime.now() + timedelta(days=days)
        for event in filter(lambda event: event['start'] < then, events):
            await channel.send(f'{event["title"]}, {event["prof"]} - {event["start"].strftime("%A")} {event["time"]}: {event["teams_link"]}')

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.content.startswith('-'):
            # got a command, parse it
            args = message.content.split(' ')
            if args[0] == '-quote':
                await self._quote_command(message.channel, args)

            if args[0] == '-calendar':
                await self._calendar_command(message.channel, args)

    async def on_ready(self):
        print('Kurisu ready uwu')
        schedule.every().day.at('00:00').do(self._update_schedule)

    def _notify_lecture(self, event):
        asyncio.run_coroutine_threadsafe(get_channel(self.notify_channel).send(f'Lesson {event["title"]} starting in 10 minutes @everyone ({events["teams_link"]})'), self.loop)

    def _update_schedule(self):
        print('Updating daily schedule')
        schedule.clear('daily_events')
        then = datetime.now() + timedelta(days=1)
        daily_events = filter(lambda e: e['start'] < then, self.scraper.scrape())
        for event in daily_events:
            hour = (event['start'] - timedelta(minutes=10)).strftime('%H:%M')
            schedule.every().day.at(hour).do(
                self._notify_lecture, event
            ).tag('daily_events')
            print(f'Scheduled {event["title"]} at {hour}')

    def run(self, token):
        print('Starting Kurisu')
        self.scheduler_thread.start()
        super(KurisuBot, self).run(token)


if __name__ == '__main__':
    env = environs.Env()
    env.read_env()
    kurisu = KurisuBot(int(env('NOTIFY_CHANNEL')))
    kurisu.run(env('DISCORD_TOKEN'))
