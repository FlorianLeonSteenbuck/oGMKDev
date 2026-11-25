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

# The lists below are per dialect: the words that are keywords there. The MySQL list above is
# Howl's; the others are curated from each dialect's reserved and common words, not complete
# copies of their grammars. A word that is no keyword of a dialect is an identifier there.
ANSI_KEYWORDS = frozenset("""
add all alter and any as asc between both by case cast char character check close column commit
connect constraint create cross current current_date current_time current_timestamp current_user
cursor database date decimal default delete desc distinct drop else end escape except exec
execute exists extract false fetch float for foreign from full grant group having in index inner
insert int integer intersect interval into is join key language left like local natural no not
null numeric of offset on only open or order outer output overlaps precision primary prior
privileges procedure real references release right rollback rows schema select session set
smallint some table temporary then time timestamp to trailing union unique unknown update using
values varchar varying view when whenever where with work
""".split())
POSTGRESQL_KEYWORDS = ANSI_KEYWORDS | frozenset("""
analyze array bigint bigserial boolean bytea cidr concurrently cube do explain filter following
freeze function ilike immutable inet jsonb json lateral listen materialized notify nulls partition
plpgsql preceding range recursive refresh returning returns rollup savepoint serial smallserial
stable symmetric tablesample text trigger unbounded unlisten uuid verbose volatile window over
begin commit macaddr first last
""".split())
MSSQL_KEYWORDS = ANSI_KEYWORDS | frozenset("""
absolute apply begin bit catch clustered datetime datetime2 datetimeoffset declare deleted end
go goto identity identity_insert if image inserted merge matched money next nchar nolock
nonclustered ntext nvarchar option output pivot print prior proc procedure raiserror recompile
return rownumber rowversion smalldatetime smallmoney throw tran transaction top try unpivot use
waitfor while xml else relative function trigger cursor
""".split())
ORACLE_KEYWORDS = ANSI_KEYWORDS | frozenset("""
blob body clob connect dual exception exit loop level minus mode nclob nextval currval nvarchar2
number package pctfree prior raise raw rowid rownum start storage synonym sysdate systimestamp
tablespace varchar2 when cursor declare begin end function procedure trigger sequence
""".split())
HIVE_KEYWORDS = ANSI_KEYWORDS | frozenset("""
array binary bigint boolean clustered cluster collection directory distribute double explode
external fields file format function items jar keys location map metadata msck overwrite
partitioned partition regexp repair rlike row delimited serde serdeproperties sort sorted stored
string struct tblproperties terminated tinyint uses view lateral skewed inputformat outputformat
""".split())
KEYWORDS_BY_DIALECT = {
    "generic": ANSI_KEYWORDS,
    "mysql": KEYWORDS,
    "mariadb": KEYWORDS,
    "postgresql": POSTGRESQL_KEYWORDS,
    "mssql": MSSQL_KEYWORDS,
    "oracle": ORACLE_KEYWORDS,
    "apache-hive": HIVE_KEYWORDS,
}


def keywords_for(dialect):
    """The keyword set of a dialect; an unknown or missing dialect gets the generic set."""
    return KEYWORDS_BY_DIALECT.get(dialect or "generic", ANSI_KEYWORDS)
