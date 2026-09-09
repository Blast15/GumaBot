class DomainError(Exception):
    """Safe message that may be displayed to the player."""


class InsufficientFunds(DomainError):
    def __init__(self):
        super().__init__("You do not have enough currency.")


class InsufficientEnergy(DomainError):
    def __init__(self):
        super().__init__("Not enough energy. Check /cooldowns or /buypack.")


class CardNotOwned(DomainError):
    def __init__(self):
        super().__init__("That card does not belong to you.")


class CardLocked(DomainError):
    def __init__(self):
        super().__init__("That card is currently locked in another activity.")


class CooldownActive(DomainError):
    def __init__(self, due: int):
        super().__init__(f"Available <t:{due}:R>.")


class AlreadyClaimed(DomainError):
    def __init__(self):
        super().__init__("This reward has already been claimed.")


class ListingUnavailable(DomainError):
    def __init__(self):
        super().__init__("This listing is no longer available.")


class InvalidState(DomainError):
    def __init__(self):
        super().__init__("This action is unavailable in the current state.")


class TradeExpired(InvalidState):
    pass


class AuctionEnded(InvalidState):
    pass


class ProviderUnavailable(DomainError):
    def __init__(self):
        super().__init__("Card data service is temporarily unavailable. Please try again later.")
