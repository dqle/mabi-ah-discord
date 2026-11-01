import discord
import settings
import json
import time
from collections import Counter
from discord.ext import commands, tasks
import database
from query_mabi_base import *

logger = settings.logging.getLogger("bot")

#-----------------------------------------
# Class:       AddItemModal
# Description: Use for ah_add_item command
#-----------------------------------------

class AddItemModal(discord.ui.Modal, title="Add Item"):
    item_name  = discord.ui.TextInput(label="Item Name", required=True, max_length=100, style=discord.TextStyle.short)
    item_id    = discord.ui.TextInput(label="Item ID", required=True, max_length=100, style=discord.TextStyle.short)
    item_price = discord.ui.TextInput(label="Item Price", required=True, max_length=100, style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        item_price = parse_price(self.item_price.value)
        if item_price is None:
            await interaction.response.send_message(
                f"Item price must be a number (got `{self.item_price}`).", ephemeral=True
            )
            return

        # Seed a one-interval lookback so the baseline total only counts the listings
        # that the alert loop will query on its first run (no duplicate alerts)
        current_time = int(time.time()) - settings.AH_ALERT_INTERVAL
        auction_house = query_item_from_mabi_base(int(self.item_id), current_time)
        total_result  = auction_house['total']

        database.insert_item(
            item_id      = int(self.item_id),
            name         = self.item_name,
            price        = item_price,
            last_match   = current_time,
            total_result = total_result,
        )
        await interaction.response.send_message(f"Added: `{self.item_name}` (ID: `{self.item_id}`) at `{item_price:,}` by {interaction.user.mention}")
        
    async def on_error(self, interaction: discord.Interaction, error):
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        logger.error(f"Error in AddItemModal: {error}")


#-----------------------------------------
# Class:       EditItemModal
# Description: Use for ah_edit_item command.
#-----------------------------------------

class EditItemModal(discord.ui.Modal):
    def __init__(self, item_name, item_id, item_price):
        super().__init__(title=f"Editing Item ID: {item_id}")
        self.original_item_name_value = item_name
        self.item_id_value = item_id
        self.original_item_price_value = item_price

        self.new_item_name = discord.ui.TextInput(
            label="Item Name",
            default=str(item_name),
            required=False,
            max_length=100,
            style=discord.TextStyle.short
        )
        self.new_item_price = discord.ui.TextInput(
            label="Item Price",
            default=f"{int(item_price):,}",   # the column stores an int, the modal shows "1,500"
            required=True,
            max_length=100,
            style=discord.TextStyle.short
        )

        self.add_item(self.new_item_name)
        self.add_item(self.new_item_price)

    async def on_submit(self, interaction: discord.Interaction):
        original_item_name_value  = self.original_item_name_value
        original_item_price_value = self.original_item_price_value
        new_item_name_value  = self.new_item_name.value
        item_id_value        = self.item_id_value
        new_item_price_value = parse_price(self.new_item_price.value)

        if new_item_price_value is None:
            await interaction.response.send_message(
                f"Item price must be a number (got `{self.new_item_price.value}`).", ephemeral=True
            )
            return

        database.update_item(item_id_value, new_item_name_value, new_item_price_value)

        await interaction.response.send_message(f"Edited: `{original_item_name_value}` -> `{new_item_name_value}` (ID: `{item_id_value}`) from `{original_item_price_value:,}` -> `{new_item_price_value:,}` by {interaction.user.mention}")
        
    async def on_error(self, interaction: discord.Interaction, error):
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        logger.error(f"Error in EditItemModal: {error}")

#-----------------------------------------
# Function: parse_price()
# Description:
#   Prices are stored as BIGINT in PostgreSQL, but the modal inputs are free
#   text that users type with thousands separators ("1,500"). Turn that into
#   an int, and treat empty/blank as "not set" (None).
#-----------------------------------------

def parse_price(value):
    """Turn a price the user typed into an int; empty/blank means "not set"."""
    if value is None:
        return None
    cleaned = str(value).replace(",", "").strip()
    return int(cleaned) if cleaned else None

#-----------------------------------------
# Function: format_price_summary()
# Description:
#   Compact price spread of a price list, cheapest first, with duplicates
#   collapsed into a count. Example: "1 x6, 5, 5,000 x2 (+1 higher)"
#-----------------------------------------

def format_price_summary(prices, top=None):
    top = settings.AH_ALERT_SUMMARY_SIZE if top is None else top
    if not prices:
        return "none"
    counts   = Counter(prices)
    cheapest = sorted(counts)[:top]
    parts    = [f"{p:,}" + (f" x{counts[p]}" if counts[p] > 1 else "") for p in cheapest]
    summary  = ", ".join(parts)
    hidden   = len(prices) - sum(counts[p] for p in cheapest)
    return summary if hidden <= 0 else f"{summary} (+{hidden} higher)"

#-----------------------------------------
# Function: build_alert_embed()
# Description:
#   Collapses every qualifying listing found in one polling cycle into a
#   single message: headline price + price summary of the new listings and
#   of every other listing currently in the query window.
#-----------------------------------------

def build_alert_embed(item_name, new_prices, all_prices, watch_price):
    embed = discord.Embed(
        title=f"{item_name} is at {min(new_prices):,}",
        colour=discord.Colour.green(),
    )
    embed.add_field(
        name   = f"New listings below watch price ({len(new_prices)})",
        value  = format_price_summary(sorted(new_prices)),
        inline = False,
    )
    embed.add_field(
        name   = f"All listings in window ({len(all_prices)})",
        value  = format_price_summary(sorted(all_prices)),
        inline = False,
    )
    embed.add_field(name="Watch price", value=f"{watch_price:,}", inline=True)
    embed.add_field(name="Cheapest now", value=f"{min(all_prices):,}", inline=True)
    embed.set_footer(text=f"Alerted {len(new_prices)} new listing(s) - {len(all_prices)} listing(s) in window")
    return embed

#-----------------------------------------
# Function: discord_run()
# Commands: ah_ping, ah_list, ah_add_item, ah_edit_item, ah_delete_item
#-----------------------------------------

def discord_run():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
    channel = None

    @bot.event
    async def on_ready():
        nonlocal channel
        channel = bot.get_channel(settings.DISCORD_CHANNEL_ID)
        bot.tree.copy_global_to(guild=settings.DISCORD_SERVER_ID)
        await bot.tree.sync(guild=settings.DISCORD_SERVER_ID)
        logger.info(f"User: {bot.user} (ID: {bot.user.id})" )
        if not ah_alert_channel.is_running():
            ah_alert_channel.start()
    
    @bot.command()
    async def ah_ping(ctx):
        """ Answers with pong """
        await ctx.send("pong")
    
    @bot.tree.command()
    async def ah_list(interaction: discord.Interaction):
        ah_list = database.get_watchlist()
        await interaction.response.send_message("Currently Watching: ```{}```".format(json.dumps(ah_list, indent=2, default=str)))

    @bot.tree.command()
    async def ah_add_item(interaction: discord.Interaction):
        await interaction.response.send_modal(AddItemModal())

    @bot.tree.command()
    async def ah_edit_item(interaction: discord.Interaction, item_id: int):
        item = database.find_item_by_id(item_id)
        if not item:
            await interaction.response.send_message(f"No watched item with ID `{item_id}`.", ephemeral=True)
            return
        await interaction.response.send_modal(EditItemModal(item['name'], item['id'], item['price']))

    @bot.tree.command()
    async def ah_delete_item(interaction: discord.Interaction, item_id: int):
        item = database.find_item_by_id(item_id)
        if not item:
            await interaction.response.send_message(f"No watched item with ID `{item_id}`.", ephemeral=True)
            return
        database.delete_item(item_id)
        await interaction.response.send_message(f"Delete Item: {item['name']} ({item_id}) by {interaction.user.mention}")

    @tasks.loop(seconds=settings.AH_ALERT_INTERVAL)
    async def ah_alert_channel():
      item_list = database.get_watched_items()
      for item in item_list:
          current_time      = int(time.time())
          item_name         = item["name"]
          item_id           = str(item["id"])
          item_price        = parse_price(item["price"])
          item_last_match   = int(item["last_match"]) if item.get("last_match") else current_time - settings.AH_ALERT_INTERVAL
          last_alert_price  = parse_price(item.get("last_alert_price"))
          alerted_listings  = {str(listing_id) for listing_id in (item.get("alerted_listings") or [])}

          try:
              auction_house    = query_item_from_mabi_base(item_id, item_last_match)
              new_total_result = auction_house['total']
              results          = auction_house['results']   # sorted by ItemPrice, Ascending

              # Listings that already left the query window can never show up again,
              # so forget them to keep alerted_listings from growing forever
              current_listing_ids = {str(listing["listingId"]) for listing in results}
              alerted_listings   &= current_listing_ids

              # Collect every qualifying listing first, then send ONE collapsed
              # message per watched item per polling cycle
              new_prices = []
              all_prices = []
              for listing in results:
                  listing_id = str(listing["listingId"])
                  price      = int(listing["price1"])
                  all_prices.append(price)

                  # Each individual listing is alerted exactly once, no matter how many
                  # consecutive polling windows it stays the cheapest one in
                  if listing_id in alerted_listings:
                      continue

                  # Alert only when the new listing is cheaper than the watch price.
                  # A brand new listing at the same low price has its own listingId,
                  # so it is alerted as well.
                  if price >= item_price:
                      continue

                  new_prices.append(price)
                  alerted_listings.add(listing_id)

              if new_prices:
                  last_alert_price = min(new_prices)
                  await channel.send(embed=build_alert_embed(item_name, new_prices, all_prices, item_price))
                  logger.info(f"Alert: {item_name} (ID: {item_id}) {len(new_prices)} new listing(s) "
                              f"at {format_price_summary(sorted(new_prices))} (watch {item_price:,})")

              #Update the last_match time to the current time and new total result
              database.update_last_match(item_id, current_time, new_total_result, last_alert_price, alerted_listings)
          except Exception as error:
              # Keep watching the same window: last_match/total_result are left untouched
              logger.error(f"Alert loop skipped {item_name} (ID: {item_id}): {error}")
              # A dead database connection is not an API problem: reconnect so the
              # next item in the list is not skipped for the same stale connection
              try:
                  database.connect(reopen=True)
              except Exception as db_error:
                  logger.error(f"Database reconnect failed: {db_error}")


    bot.run(settings.DISCORD_API_TOKEN, root_logger = True)

if __name__ == "__main__":
    discord_run()