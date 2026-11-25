"""SQL keyword list, taken from Howl's SQL lexer.

Source: bundles/basic_modes/lexers/sql.lua in https://github.com/howl-editor/howl
(MIT license, Copyright 2006-2012 Mitchell and the Howl developers).
Generated once by splitting the word_match table; see THIRD_PARTY_NOTICES.md.
"""

KEYWORDS = frozenset("""
add all alter analyze and as asc asensitive before between bigint binary
blob both by call cascade case change char character check collate column
condition connection constraint continue convert create cross current_date
current_time current_timestamp current_user cursor database databases
day_hour day_microsecond day_minute day_second dec decimal declare default
delayed delete desc describe deterministic distinct distinctrow div double
drop dual each else elseif enclosed escaped exists exit explain false fetch
float for force foreign from fulltext goto grant group having high_priority
hour_microsecond hour_minute hour_second if ignore in index infile inner
inout insensitive insert int integer interval into is iterate join key keys
kill leading leave left like limit lines load localtime localtimestamp lock
long longblob longtext loop low_priority match mediumblob mediumint
mediumtext middleint minute_microsecond minute_second mod modifies natural
no_write_to_binlog not null numeric on optimize option optionally or order
out outer outfile precision primary procedure purge read reads real
references regexp rename repeat replace require restrict return revoke right
rlike schema schemas second_microsecond select sensitive separator set show
smallint soname spatial specific sql sql_big_result sql_calc_found_rows
sql_small_result sqlexception sqlstate sqlwarning ssl starting straight_join
table terminated text then tinyblob tinyint tinytext to trailing trigger
true undo union unique unlock unsigned update usage use using utc_date
utc_time utc_timestamp values varbinary varchar varcharacter varying when
where while with write xor year_month zerofill
""".split())
