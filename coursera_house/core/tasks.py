from __future__ import absolute_import, unicode_literals

import copy
import json

import requests
from celery import task
from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse

from .models import Setting

TOKEN = settings.SMART_HOME_ACCESS_TOKEN  
header = {'Authorization': 'Bearer {}'.format(settings.SMART_HOME_ACCESS_TOKEN)}
GET_ALL_CONTROLLERS = settings.SMART_HOME_API_URL


class Processor(object):
    """ Класс логики работы с умным домом """

    # Processor является синглтоном
    obj = None

    def __new__(cls, *args, **kwargs):
        if not cls.obj:
            cls.obj = super().__new__(cls)
        return cls.obj

    storage = {
        'hot_water_target_temperature': 80,
        'bedroom_target_temperature': 21
    }  # хранилище данных на сервере

    @classmethod
    def _read_all_controllers(cls):
        """ Функция опроса всех контроллеров """

        try:  # отправка запроса на сервер

            r = requests.get(GET_ALL_CONTROLLERS, headers=header)
            print(f'Отправлен запрос по адресу {GET_ALL_CONTROLLERS}')

            for position in r.json()['data']:  # парсинг ответа от сервера
                if position['name'] not in cls.storage:
                    cls.storage[position['name']] = None

                cls.storage[position['name']] = position['value']  # любые данные записываем в хранилище

            try:  # берем значения из БД, которые заполняются через форму
                cls.storage['hot_water_target_temperature'] = Setting.objects.get(
                    controller_name='hot_water_target_temperature').value
                cls.storage['bedroom_target_temperature'] = Setting.objects.get(
                    controller_name='bedroom_target_temperature').value
            except Setting.DoesNotExist:
                pass

        except json.decoder.JSONDecodeError:  # проверка того что данные прошли действительно валидные 
            print(f'Запрос не дошёл до адреса')
            return HttpResponse(content='Bad Gateway', status=502)
        return cls.storage

    @classmethod
    def control_bedroom_light(cls, val):  # включаем свет если датчик дыма отключен(см. views.py)
        if not cls.storage['smoke_detector']:
            return val
        else:
            return False

    @classmethod
    def control_bathroom_light(cls, val):  # включаем свет если датчик дыма отключен(см. views.py)
        if not cls.storage['smoke_detector']:
            return val
        else:
            return False

    @classmethod
    def control_bedroom_target_temperature(cls, val):  # пишем в БД требуемую температуру(см. views.py)
        try:
            s = Setting.objects.filter(controller_name='bedroom_target_temperature')
            if val != s[0].value:
                s.update(value=val)
                print('Новые данные по температуре в комнате')
        except Setting.DoesNotExist:
            Setting.objects.create(controller_name='bedroom_target_temperature', label='Желаемая температура в спальне',
                                   value=val)
        return val

    @classmethod
    def control_hot_water_target_temperature(cls, val):  # пишем в БД требуемую температуру(см. views.py)
        try:
            s = Setting.objects.filter(controller_name='hot_water_target_temperature')
            if val != s[0].value:
                s.update(value=val)
                print('Новые данные по температуре горячей воды')
        except Setting.DoesNotExist:
            Setting.objects.create(controller_name='hot_water_target_temperature',
                                   label='Желаемая температура горячей воды', value=val)
        return val

    @classmethod
    def check_signalization(cls):  # проверяем все датчики на наличие аварийных ситуаций

        # логика работы при температуре ниже требуемой
        if cls.storage['bedroom_temperature'] > 1.1 * cls.storage['bedroom_target_temperature']:
            cls.storage['air_conditioner'] = True
        if cls.storage['bedroom_temperature'] < 0.9 * cls.storage['bedroom_target_temperature']:
            cls.storage['air_conditioner'] = False

        # логика работы при температуре ниже требуемой
        try:
            if cls.storage['boiler_temperature'] < 0.9 * cls.storage['hot_water_target_temperature']:
                cls.storage['boiler'] = True
            if cls.storage['boiler_temperature'] >= 1.1 * cls.storage['hot_water_target_temperature']:
                cls.storage['boiler'] = False
        except TypeError:
            pass


        if cls.storage['leak_detector']:  # логика работы при протечке
            send_mail(subject='Авария дома', message='В доме случилась протечка воды', from_email='from@example.com',
                      recipient_list=[settings.EMAIL_RECEPIENT, ])
            cls.storage['cold_water'] = False
            cls.storage['hot_water'] = False

        if not cls.storage['cold_water']:  # логика работы при отключенной холодной воде
            cls.storage['boiler'] = False
            cls.storage['washing_machine'] = 'off'

        if cls.storage['smoke_detector']:  # логика работы при включенном датчике задымления
            cls.storage['air_conditioner'] = False
            cls.storage['bedroom_light'] = False
            cls.storage['bathroom_light'] = False
            cls.storage['boiler'] = False
            cls.storage['washing_machine'] = 'off'

        if cls.storage['outdoor_light'] < 50 and cls.storage['bedroom_light'] is False and cls.storage['curtains'] != 'slightly_open':
            cls.storage['curtains'] = 'open'
        elif cls.storage['outdoor_light'] > 50 and cls.storage['curtains'] != 'slightly_open':
            cls.storage['curtains'] = 'close'

    @classmethod
    def _write_all_controllers(cls, some_data):  # метод для записи данных в контроллеры
        data_in_controllers = []

        for key in some_data.keys():
            data_in_controllers.append({'name': key, 'value': some_data[key]})

        data_to_send = json.dumps({'controllers': data_in_controllers})

        requests.post(GET_ALL_CONTROLLERS, data=data_to_send, headers=header)
        print('Запрос отправлен на сервер')


@task()
def smart_home_manager():
    d1 = copy.deepcopy(Processor._read_all_controllers())  # получаю данные из запроса к API
    print('Данные полученные от сервера:')
    print(d1)
    Processor.check_signalization()
    d2 = copy.deepcopy(Processor.storage)
    print('Данные после обработки:')
    print(d2)
    for key in d1:
        if d1[key] == d2[key]:
            d2.pop(key, None)
    if len(d2) > 0:
        Processor._write_all_controllers(d2)
        print('Данные отправлены на сервер')
        print('Данные для отправки:')
        print(d2)
    else:
        print('Нет новых данных для сервера')
