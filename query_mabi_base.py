import requests

API_URL                = "https://api.na.mabibase.com/graphql?t=1"
PERSISTED_QUERY_SHA256 = "e42f50b9ab00b0e7b820afbaae91c07722178ed6b0d3aa3b578c8cc4edfe3a84"
PAGE_SIZE              = 25   # must match the persisted query's pagination.pageSize

#-----------------------------------------
# Function: to_mabi_timestamp()
# Description:
#   MabiBase compares the `ListedAfter` filter against epoch MILLISECONDS,
#   while this bot stores epoch seconds in PostgreSQL. Sending seconds (e.g.
#   1793567684) makes the filter point at Jan 1970, so every current
#   listing matches and new listings are never detected.
#-----------------------------------------

def to_mabi_timestamp(epoch_seconds):
    return int(int(epoch_seconds) * 1000)

def craft_request_body(item_id, item_last_match_ms):
    request_body = [{
        "operationName": "auctionHouseSearch",
        "variables": {
          "server": "mabius6",
          "filters": [
            {
              "type": "ItemId",
              "comparator": "eq",
              "value": f"{item_id}"
            },
            {
              "type": "ListedAfter",
              "value": f"{item_last_match_ms}"
            }
          ],
          "pagination": {
            "pageSize": PAGE_SIZE,
            "pageIndex": 0
          },
          "sort": {
            "attribute": "ItemPrice",
            "direction": "Ascending"
          }
        },
        "extensions": {
          "persistedQuery": {
            "version": 1,
            "sha256Hash": PERSISTED_QUERY_SHA256
          }
        }
      }]
    return request_body

#-----------------------------------------
# Function: query_item_from_mabi_base()
# Description:
#   Returns the parsed `auctionHouse` object ({total, results}) for an item.
#   `item_last_match` is the epoch-seconds value stored in ah_items.
#-----------------------------------------

def query_item_from_mabi_base(item_id, item_last_match):
    request_body = craft_request_body(item_id, to_mabi_timestamp(item_last_match))
    response     = requests.post(API_URL, json=request_body, timeout=15)
    response.raise_for_status()
    payload = response.json()

    # Batched persisted queries come back as a list: [{"data": {...}}]
    if isinstance(payload, list):
        payload = payload[0] if payload else {}

    if payload.get("errors"):
        raise RuntimeError(f"MabiBase GraphQL error: {payload['errors']}")

    auction_house = (payload.get("data") or {}).get("auctionHouse")
    if not auction_house:
        raise RuntimeError(f"Unexpected MabiBase response: {payload}")

    return auction_house
