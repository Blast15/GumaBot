# GumaBot command reference

Generated from registered discord.py slash commands. Arguments in brackets are optional.

| Command | Arguments | Description |
| --- | --- | --- |
| `/achievements` | `[set_id]` | View achievement progress |
| `/admin sync_cards` | `set_id` | Synchronize a card set into local cache (bot owner only) |
| `/auction bid` | `auction amount` | Reserve coins for an auction bid |
| `/auction cancel` | `auction` | Cancel your active auction if it has no bids |
| `/auction create` | `code price [hours] [increment] [buyout]` | Create an auction for one available card |
| `/auction info` | `auction` | Inspect an auction |
| `/avatarchoice` | `avatar` | Choose your original GumaBot trainer avatar |
| `/bag` | `[set_id]` | View Journey consumables; use /journey potion to heal |
| `/balance` | `[set_id]` | View coins, Aura and energy |
| `/blackjack` | `[wager] [session]` | Play blackjack with virtual coins only; maximum wager 500 |
| `/buyitem` | `item [quantity]` | Purchase items using virtual coins |
| `/buypack` | `` | Buy one energy for 40 coins |
| `/cardtrend` | `card_id [days]` | View actual market sale statistics for 7 or 30 days |
| `/checkgrade` | `code` | Check grading ETA or your certificate |
| `/collection` | `[set_id]` | View collection totals and rarity distribution |
| `/cooldowns` | `[set_id]` | View cooldown timestamps and energy ETA |
| `/daily` | `` | Claim your rolling 24-hour daily reward |
| `/deck` | `[codes]` | Set exactly five public codes separated by spaces, or view your deck |
| `/duel` | `[user] [duel_id]` | Challenge a player or resume a persisted duel |
| `/duelprofile` | `[set_id]` | View duel wins, losses and rating |
| `/favorite` | `code [enabled]` | Protect or unprotect a card from bulk system sale |
| `/find` | `name` | Find cards by name in your inventory |
| `/fuse` | `code1 code2 code3` | Fuse three raw duplicate instances into an improved card |
| `/give` | `user [amount] [code]` | Transfer coins or an available card to another player |
| `/grade` | `code [lane] [coupon]` | Submit a raw card for timed grading |
| `/guide` | `` | Seven-page GumaBot tutorial |
| `/gym` | `[leader]` | Challenge one of eight original gym leaders |
| `/help` | `` | List the commands actually registered in this bot |
| `/inventory` | `[page] [name] [set_id] [rarity] [condition_name] [graded] [duplicate] [sort]` | Filter, sort and page through your card instances |
| `/items` | `[set_id]` | View your shop items |
| `/itemshop` | `[set_id]` | View item prices |
| `/journey` | `[action]` | Explore encounters, rest or use a potion |
| `/leaderboard` | `[metric] [page]` | Rank trainers by economy, collection or gameplay |
| `/level` | `[set_id]` | View XP and progress to level 50 |
| `/market browse` | `[page]` | Browse available listings |
| `/market buy` | `listing` | Buy an active listing atomically |
| `/market list` | `code price` | List one of your available cards |
| `/market remove` | `listing` | Remove your active listing |
| `/missing` | `[set_id]` | List missing cards from a locally cached set |
| `/mysterybox` | `` | Open a mystery box from your items |
| `/namepokemon` | `[session]` | Identify a Pokémon from its provider image |
| `/openpack` | `[set_id]` | Open five cards using one energy |
| `/packs` | `[set_id]` | List provider card sets |
| `/peek` | `code` | Offer a spare duplicate for another player to claim |
| `/pickcard` | `[session]` | Choose one of three cards every thirty minutes |
| `/play` | `` | Open your trainer dashboard |
| `/quests` | `[set_id]` | View three daily quests and automatic rewards |
| `/quiz` | `[session]` | Answer up to ten questions in a persisted session |
| `/quizstats` | `[set_id]` | View quiz accuracy and streaks |
| `/reminder` | `kind enabled` | Opt into or out of a personal reminder |
| `/report` | `` | Send bug feedback into the local database |
| `/resetpack` | `` | Compatibility alias: buy one energy for 40 coins |
| `/search` | `code` | Inspect a card instance using its public code |
| `/season` | `[set_id]` | View current monthly season and Hall of Fame |
| `/sell` | `` | Preview a bulk sale of up to 25 unprotected raw cards |
| `/serverleaderboard` | `[set_id]` | Compare average XP of registered server players |
| `/setchannel` | `channel [enabled]` | Configure server drops in a channel |
| `/setcompletion` | `[set_id]` | View locally known set completion |
| `/shop browse` | `[page]` | Browse available listings |
| `/shop buy` | `listing` | Buy an active listing atomically |
| `/shop list` | `code price` | List one of your available cards |
| `/shop remove` | `listing` | Remove your active listing |
| `/showcase` | `` | Render your nine highest-graded cards |
| `/start` | `` | Create your trainer and claim your starter pack once |
| `/swapcodes` | `first second` | Swap two of your available card codes atomically |
| `/tint` | `code color` | Apply a tint token to a card without changing the original image |
| `/trade` | `[user] [action] [trade_id] [kind] [reference] [amount]` | Invite, accept, inspect or update an escrow-backed trade |
| `/upcoming` | `[set_id]` | View verified cached upcoming release dates |
| `/useitem` | `item` | Use an energy booster or cosmetic badge |
| `/wishlist add` | `card_id` | Add a catalog card to your wishlist |
| `/wishlist list` | `` | Show your wishlist |
| `/wishlist remove` | `card_id` | Remove a catalog card from your wishlist |

