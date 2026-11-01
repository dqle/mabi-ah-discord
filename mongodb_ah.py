import pymongo
import settings

def get_collection():
    # Create a connection using MongoClient
    client = pymongo.MongoClient(settings.MONGODB_CONNECTION_STRING)

    # Get the database
    database = client['mabi_ah']

    # Get the collection
    collection = database['ah_items']

    # Check if the 'id' index exists
    indexes = collection.index_information()
    if 'id_1' not in indexes:
        # Create a unique index on the 'id' field
        collection.create_index("id", unique=True)

    return collection

def get_all_items_in_collection(collection, include_last_match):
    if include_last_match == True:
        return list(collection.find({},{"_id" : 0 }))
    else:
        return list(collection.find({},{"_id" : 0, "last_match": 0, "alert": 0, "alerted_listings": 0}))
        
def insert_item(collection, item):
    collection.insert_one(item)

def update_item(collection, item_id, new_name, new_price):
    query = { "id": f"{item_id}" }
    new_value = { 
        "$set": {
             "name" : f"{new_name}",
             "price": f"{new_price}",
        } 
    }
    collection.update_one(query, new_value)

def update_last_match(collection, item_id, item_last_match, total_result, last_alert_price=None, alerted_listings=None):
    query = { "id": f"{item_id}" }
    new_value = { 
        "$set": {
             "last_match" : f"{item_last_match}",
             "total_result": f"{total_result}",
        } 
    }

    # Only touch the alert bookkeeping when the caller provides it,
    # so a failed API call cannot wipe the alerted history
    if last_alert_price is not None:
        new_value["$set"]["last_alert_price"] = f"{last_alert_price}"
    if alerted_listings is not None:
        new_value["$set"]["alerted_listings"] = [f"{listing_id}" for listing_id in alerted_listings]

    collection.update_one(query, new_value)

def delete_item(collection, item_id):
    query = { "id": f"{item_id}" }
    collection.delete_one(query)

def find_item_by_id(item_id, collection):
    return collection.find_one({"id": f"{item_id}"})