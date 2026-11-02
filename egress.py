"""The one network helper the idealista module needs: the Accept-Language
its sessions send. idealista is a Spanish site and DataDome refuses a
browser whose language list does not fit the connection, so every session
announces the list a desktop Chrome in Spain sends — on your own
connection or on IDEALISTA_PROXY alike."""

SPANISH = "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7"


def site_accept_language(site=None):
    return SPANISH


def accept_language(proxy=None, country=None):
    return SPANISH
