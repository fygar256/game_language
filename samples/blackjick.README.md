# blackjick

I made a program (imitation) to play the card game blackjack with a computer, but I don't know the kind of blackjack you play in casinos,
and after being told about it, I tried to make it again, but when I searched the web, I found that the interaction with the dealer was unexpectedly complicated, 
so I stopped development and left the original program as 'BlackJick', since it is playable as it is. 

Jick is a black cat I used to have, and I left it on the wall of the kindergarten next door and went to the convenience store, and it disappeared. I dedicate this program to Jick.

It is written in python.

Python: Download the script. run it as `python blackjick.py`

This program is a basic artificial intelligence version that makes predictions using classical probability theory.

# How to play

At first, both the computer and the player are dealt two cards.

The opponent's cards cannot be seen. You draw cards from the pile so that the total of your hand does not exceed 21. The computer draws cards based on probability calculations.

There is one Joker, which can take on any value between 0 and 10. 

The Ace is always 1. It cannot become 11 like in Blackjack. The Jack, Queen, and King are all calculated as 10. 

The player with the higher total of their cards wins, but if it exceeds 21 you are out. If the computer and the player have the same score, the player with the Joker wins.

Draw a card in 1, and play against the computer in 2.
