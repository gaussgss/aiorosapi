#!/usr/bin/env python3
# -+- coding: utf-8 -+-


import asyncio
from aiorosapi.protocol import create_ros_connection


async def main():
    conn = await create_ros_connection(
        host='192.168.90.1',
        port=8728,
        username='admin',
        password=''
    )

    data = await conn.talk_one('/system/routerboard/print')
    print("Routerboard info:")
    for k, v in data.items():
        print('{:>20s}: {}'.format(k, v))

    data = await conn.talk_all('/interface/ethernet/print')
    print("Ethernet interfaces:")
    for item in data:
        print("{:>20s}: {}".format(item['.id'], item['name']))

    await conn.disconnect()
    await conn.wait_disconnect()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
