# Regex mass editing

Open **Mass Edit** on the Cards page. Choose **All cards**, **Selected cards**,
**Search results**, or **Favorites**. All scopes use the current TCG/OCG region.
Use Ctrl-click or Shift-click in the card list to select multiple cards before
opening the dialog. Search results uses the last executed search currently
displayed in the list; it is empty when no search is displayed or the favorites
filter is active. Favorites includes every favorite, regardless of the search.

Enter a Python regular expression and replacement text (capture references such
as `\1` are supported), then choose names, descriptions, or both. Empty
replacement text deletes matches. Existing text edits are the starting text.

Click **Preview Changes** to see the number of affected cards and replacements.
Choose an affected card to inspect its full before/after text and line differences.
The **Differences** block highlights removed lines in red and added lines in green,
with subtle matching backgrounds. Diff headers are blue and bold; newline notes
are muted and italic. Colors adapt to light and dark themes. The `-` and `+`
prefixes remain visible so changes can also be identified without color.

Identical replacements do not count as changes. Previewing does not write game
files. **Apply Changes** is enabled only after a preview with actual changes;
changing any input or scope requires another preview. Applying writes only the
chosen cards and rebuilds card metadata once for the batch.

## Manual verification

On a configured game installation:

1. Search for a group of cards, select two using Ctrl-click, and open Mass Edit.
   Check the selected and search-result scope counts against the list.
2. Preview a replacement in names and descriptions. Inspect several cards and
   their differences. Confirm removed lines are red, additions are green, and
   headers are blue and bold in light and dark themes. Cancel and confirm text
   is unchanged.
3. Mark a card as a favorite. Preview the Favorites scope and confirm it includes
   favorites outside the current search.
4. Change a field checkbox, replacement, and scope after previewing. Check that
   Apply is disabled until a new preview. Try a malformed pattern and capture
   reference, a no-match pattern, and an empty selected scope.
5. Apply to the two selected cards. Confirm the result count matches the preview
   and other matching cards are unchanged. Verify the text in game.
6. Repeat in OCG and check that TCG cards are unchanged.

Automated coverage runs without touching the local database or game bundles:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_card*.py' -v
```
