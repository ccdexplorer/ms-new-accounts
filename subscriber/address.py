from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.mongodb import (
    Collections,
)
from ccdexplorer_fundamentals.tooter import Tooter
from pymongo import DeleteOne, ReplaceOne
from pymongo.collection import Collection
from rich.console import Console

console = Console()


class Address:
    async def address_already_exists(self, net: NET, msg: dict):
        db: dict[Collections, Collection] = (
            self.motor_mainnet if net.value == "mainnet" else self.motor_testnet
        )
        new_address = msg["address"]
        canonical_address = new_address[:29]
        address_exists = await db[Collections.all_account_addresses].find_one(
            {"_id": canonical_address}
        )
        return address_exists is not None

    async def cleanup(self):

        for net in NET:
            console.log(f"Running cleanup for {net}.")
            db: dict[Collections, Collection] = (
                self.motor_mainnet if net.value == "mainnet" else self.motor_testnet
            )

            todo_addresses = (
                await db[Collections.queue_todo]
                .find({"type": "address"})
                .to_list(length=None)
            )
            for msg in todo_addresses:
                if not (await self.address_already_exists(net, msg)):
                    await self.process_new_address(net, msg)
                await self.remove_todo_from_queue(net, msg)

    async def remove_todo_from_queue(self, net: str, msg: dict):
        db: dict[Collections, Collection] = (
            self.motor_mainnet if net.value == "mainnet" else self.motor_testnet
        )

        _ = await db[Collections.queue_todo].bulk_write(
            [DeleteOne({"_id": msg["_id"]})]
        )

    async def process_new_address(self, net: NET, msg: dict):
        self.motor_mainnet: dict[Collections, Collection]
        self.motor_testnet: dict[Collections, Collection]
        self.grpcclient: GRPCClient
        self.tooter: Tooter

        db_to_use = self.motor_testnet if net.value == "testnet" else self.motor_mainnet
        new_address = msg["address"]
        try:
            account_info = self.grpcclient.get_account_info(
                "last_final", hex_address=new_address, net=net
            )
        except Exception as e:
            tooter_message = f"{net.value}: New address failed with error  {e}."
            self.send_to_tooter(tooter_message)
            return

        canonical_address = new_address[:29]
        new_record = {
            "_id": canonical_address,
            "account_address": new_address,
            "account_index": account_info.index,
        }
        _ = await db_to_use[Collections.all_account_addresses].bulk_write(
            [ReplaceOne({"_id": canonical_address}, new_record, upsert=True)]
        )
        tooter_message = f"{net.value}: New address processed {new_address} at index {account_info.index}."
        self.send_to_tooter(tooter_message)
