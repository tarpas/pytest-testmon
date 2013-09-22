import hashlib


def get_hash(nonce):
    return hashlib.sha512('SOME DATA %s' % nonce).hexdigest()


def nonce_meets_target(nonce, target):
    """ Does hash produced from the nonce meet the target? """
    digest = get_hash(nonce)
    return digest[:target] == '0' * target


def find_nonce(target):
    """
    Simple crypto-currency-like miner that finds a nonce satisfying
    hash output requirements (hash has to start with a consecutive
    `target` number of zeros, in hexa).

    The purpose of this routine is to simulate real-life example
    of CPU intensive unit that is to be tested (and benchmarked).
    """
    assert target < 10, "Target must be less than 10."

    nonce = 0
    while True:
        if nonce_meets_target(nonce, target):
            return nonce
        nonce += 1
